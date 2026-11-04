"""The Needs your decision cards (Phase 83, plan 83-18, RESP-09, ACTV-02, D-16, D-17, D-24, 83-UI-SPEC 2 and 2a).

``list_cards`` answers one question: what needs a person in this organization. A card is one incident (one host,
alerts until an hour passes with nothing new) that has at least one action waiting for a person, or an isolation
that is done but not confirmed yet. Every line of the card carries its own ``canApprove``, ``canDeny`` and
``canConfirmIsolation``, worked out here from the caller's rights, so the browser never infers a permission.
There is no approve-all: each line is decided through the existing approve and deny routes.

What counts as waiting is one filter, ``_waiting_filter``: an approval card, a suggested row the Suggest level
parked for approval (reason ``level_suggest`` or ``settings_unreadable`` and not ``suggestionOnly``; assumption
A-83-LEVEL-SUGGEST, awaiting the user's confirmation) and an isolate row done but unconfirmed. Change it there.
Rows marked ``suggestionOnly`` (one source, vulnerabilities, file changes, correlations) never appear.

Lines of an incident that already ran appear with no flags (R4). A kill line and its retry fold into one line with
chain steps (the retry row is not a line of its own); the quarantine that was locked is folded into the kill line
it caused. Cards sort by soonest deadline, ties by incident start, newest first.

Raw Mongo handle with an explicit tenantId on every read; nothing here writes.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from . import ledger, messages, response_messages as rm, settings, views
from .scope import raw

logger = logging.getLogger(__name__)

APPROVABLE_SUGGESTION_CODES = ("level_suggest", "settings_unreadable")     # A-83-LEVEL-SUGGEST, in one place
SEED_CAP = 500                  # rows read to find the incidents that need a person
ROW_CAP = 2000                  # rows read for those incidents
LINE_CAP = 50                   # lines one card carries
RETRY, KILL_ONLY = "retry", "kill_only"
_WAITING = ("awaiting_approval", "suggested")
_RAN = ("approved", "dispatching", "executed", "verified", "failed", "undone", "rolled_back", "denied", "expired",
        "refused", "cancelled_by_stop")
_DONE = ("executed", "verified")
_FAILED = ("failed", "refused", "denied", "expired", "cancelled_by_stop")


def _now(now: Optional[datetime]) -> datetime:
    now = now or datetime.now(timezone.utc)
    now = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _inputs(row: Dict[str, Any]) -> Dict[str, Any]:
    return _dict(_dict(row.get("reason")).get("inputs"))


def _aware(value: Any) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _iso(value: Any) -> Optional[str]:
    value = _aware(value)
    return value.isoformat() if value else None


# ---------------------------------------------------------------- what needs a person (one filter)

def _waiting_filter(now: datetime) -> List[Dict[str, Any]]:
    """The Mongo conditions, any of which makes a row something a person can still decide at ``now``."""
    live = {"approval.expiresAt": {"$gt": now}, "reason.inputs.suggestionOnly": {"$ne": True}}
    return [
        {"state": "awaiting_approval", **live},
        {"state": "suggested", "reasonCode": {"$in": list(APPROVABLE_SUGGESTION_CODES)}, **live},
        {"command": "isolate_host", "state": {"$in": list(_DONE)}, "isolation.confirmedAt": None,
         "isolation.revertsAt": {"$gt": now}},
    ]


def _is_waiting_approval(row: Dict[str, Any], now: datetime) -> bool:
    """The same test as the first two conditions of ``_waiting_filter``, for a row already read."""
    if _inputs(row).get("suggestionOnly") is True:
        return False
    state = row.get("state")
    if state == "suggested" and row.get("reasonCode") not in APPROVABLE_SUGGESTION_CODES:
        return False
    if state not in _WAITING:
        return False
    expires = _aware(_dict(row.get("approval")).get("expiresAt"))
    return expires is not None and expires > now


def _isolation(row: Dict[str, Any]) -> Dict[str, Any]:
    return _dict(row.get("isolation"))


def _is_open_isolation(row: Dict[str, Any], now: datetime) -> bool:
    iso = _isolation(row)
    reverts = _aware(iso.get("revertsAt"))
    return (row.get("command") == "isolate_host" and row.get("state") in _DONE and not iso.get("confirmedAt")
            and reverts is not None and reverts > now)


# ---------------------------------------------------------------- one line

def _step_state(row: Optional[Dict[str, Any]], earlier_done: bool = True) -> str:
    """pending (not finished yet), done, failed, or skipped (it never ran because the step before it did not)."""
    if row is None:
        return "pending" if earlier_done else "skipped"
    state = row.get("state")
    if state in _DONE:
        return "done"
    if state in _FAILED:
        return "failed"
    return "pending"


def _chain_of(row: Dict[str, Any], retry: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    chain = _dict(_inputs(row).get("chain"))
    if row.get("command") != "kill_process" or chain.get("mode") not in (RETRY, KILL_ONLY):
        return None
    process = _dict(chain.get("process"))
    out: Dict[str, Any] = {"mode": chain["mode"], "steps": [], "path": chain.get("path"),
                           "process": {"name": process.get("name"), "pid": process.get("pid")}}
    if chain["mode"] == RETRY:
        first = _step_state(row)
        out["steps"] = [{"label": messages.ACTION_LABELS["kill_process"], "state": first},
                        {"label": messages.ACTION_LABELS["quarantine_file"],
                         "state": _step_state(retry, earlier_done=first != "failed")}]
    return out


def _approver(row: Dict[str, Any]) -> str:
    approver = _dict(_dict(row.get("approval")).get("approver"))
    return str(approver.get("display") or approver.get("username") or "")


def _decided_result(row: Dict[str, Any], host: Optional[str]) -> Optional[str]:
    """The result sentence of a line a person decided (83-UI-SPEC 2a), else None."""
    state = row.get("state")
    if state in ("approved", "dispatching") and _approver(row):
        return rm.fill(rm.RESULT_TEMPLATES["card_approved"], host=host or "this computer")
    if state == "denied":
        return rm.fill(rm.RESULT_TEMPLATES["card_denied"], name=_approver(row) or "a person")
    if state == "expired":
        return rm.RESULT_TEMPLATES["card_expired"]
    return None


def _consequence(row: Dict[str, Any], chain: Optional[Dict[str, Any]], waiting: bool) -> Optional[str]:
    """What happens (waiting) or what will happen without a decision (an unconfirmed isolation)."""
    command, inputs = row.get("command"), _inputs(row)
    if command == "isolate_host":
        return rm.WHAT_HAPPENS["isolation_unconfirmed" if not waiting else "isolate_host"]
    if not waiting:
        return None
    if chain is not None:
        return rm.WHAT_HAPPENS["kill_then_quarantine" if chain["mode"] == RETRY else "kill_process"]
    if command in ("kill_process", "reboot_host"):
        return rm.WHAT_HAPPENS[command]
    service = inputs.get("service")
    if command == "restart_service" and inputs.get("overBudget") and isinstance(service, str):
        return rm.fill(rm.WHAT_HAPPENS["restart_over_budget"], service=service)
    if command == "quarantine_file" and (inputs.get("protectedPath") or row.get("reasonCode") == "protected_path"):
        return rm.WHAT_HAPPENS["protected_file"]
    return None


def _line(row: Dict[str, Any], *, host: Optional[str], retry: Optional[Dict[str, Any]], can_act: bool,
          staff: bool, now: datetime) -> Dict[str, Any]:
    shown = views.present_row(row, viewer_is_platform_staff=staff, host=host, can_act=False, now=now)
    chain = _chain_of(row, retry)
    waiting = _is_waiting_approval(row, now)
    open_iso = _is_open_isolation(row, now)
    iso = _isolation(row)
    label, reason, target = shown["actionLabel"], shown["reasonText"], shown["target"]
    notice = None
    if chain is not None:
        notice = rm.NOTICES["kill_then_quarantine" if chain["mode"] == RETRY else "kill_only"]
        proc = chain["process"]
        target = f"{proc['name']} (PID {proc['pid']})" if proc.get("name") and proc.get("pid") else target
        if chain["mode"] == RETRY:
            label = rm.CHAIN_LABELS["kill_then_quarantine"]
        if reason == notice:
            reason = None                       # the info block says it; the Why line would repeat it word for word
    result = None if waiting else _decided_result(row, host) or shown["resultText"]
    if iso.get("confirmedAt"):
        result = rm.fill(rm.RESULT_TEMPLATES["isolation_confirmed"], name=_dict(iso.get("confirmedBy")).get("display")
                         or _dict(iso.get("confirmedBy")).get("username") or "a person")
    if chain is not None and retry is not None and retry.get("state") in _FAILED and chain["steps"]:
        why = rm.CHAIN_FAIL_REASONS.get(retry.get("reasonCode"), rm.CHAIN_FAIL_DEFAULT)
        result = rm.fill(rm.RESULT_TEMPLATES["chain_quarantine_failed"], reason=why)
    needs = waiting or open_iso
    return {
        "id": row["id"], "state": row.get("state"), "bucket": shown["bucket"], "command": row.get("command"),
        "label": label, "target": target, "reason": reason, "ruleId": shown["ruleId"],
        "consequenceText": _consequence(row, chain, waiting) if (waiting or open_iso) else None,
        "notice": notice, "result": result, "needsPerson": needs, "createdAt": shown["createdAt"],
        "expiresAt": _iso(_dict(row.get("approval")).get("expiresAt")) if waiting else None,
        "revertsAt": _iso(iso.get("revertsAt")) if row.get("command") == "isolate_host" else None,
        "chain": chain,
        "canApprove": bool(can_act and waiting), "canDeny": bool(can_act and waiting),
        "canConfirmIsolation": bool(can_act and open_iso),
        "confirmedAt": _iso(iso.get("confirmedAt")),
        "confirmedBy": (_dict(iso.get("confirmedBy")).get("display") or _dict(iso.get("confirmedBy")).get("username"))
        if iso.get("confirmedAt") else None,
        "blockedUntil": _iso(row.get("blockedUntil")),          # a block line's result carries {until}, filled in the browser
    }


# ---------------------------------------------------------------- one card

def _visible(row: Dict[str, Any]) -> bool:
    """A row that belongs on a card at all: it ran or is waiting, and it is not a suggestion only."""
    if row.get("kind") == "control" or row.get("shadow") or _inputs(row).get("suggestionOnly") is True:
        return False
    state = row.get("state")
    if state == "suggested":
        return row.get("reasonCode") in APPROVABLE_SUGGESTION_CODES
    return state in _WAITING or state in _RAN


def _folded(rows: List[Dict[str, Any]]) -> tuple:
    """(ids that are folded into a kill line, kill id -> its retry row). A retry is a line of its own only when
    its kill row is not on the card; a locked quarantine is folded into the kill line it caused."""
    kills = {r["id"]: r for r in rows if _chain_of(r, None) is not None}
    retry_of: Dict[str, Dict[str, Any]] = {}
    hidden: Set[str] = set()
    for row in rows:
        parent = _inputs(row).get("parentActionId")
        if parent in kills and row.get("command") == "quarantine_file":
            retry_of[parent] = row
            hidden.add(row["id"])
    for kill in kills.values():
        chain = _dict(_inputs(kill).get("chain"))
        if chain.get("mode") == RETRY and isinstance(chain.get("quarantineActionId"), str):
            hidden.add(chain["quarantineActionId"])
    return hidden, retry_of


def _card(incident_id: str, rows: List[Dict[str, Any]], incident: Optional[Dict[str, Any]],
          hosts: Dict[str, str], *, can_act: bool, staff: bool, now: datetime) -> Optional[Dict[str, Any]]:
    rows = [r for r in rows if _visible(r)]
    hidden, retry_of = _folded(rows)
    host_id = (incident or {}).get("agentId") or next(
        (str(r["targets"][0]) for r in rows if r.get("targets")), None)
    host = hosts.get(str(host_id)) if host_id else None
    lines = [_line(r, host=host, retry=retry_of.get(r["id"]), can_act=can_act, staff=staff, now=now)
             for r in rows if r["id"] not in hidden]
    lines.sort(key=lambda l: (l["createdAt"] or "", l["id"]), reverse=True)           # newest first ...
    lines.sort(key=lambda l: not l["needsPerson"])                                    # ... a person's decisions first
    if not any(l["needsPerson"] for l in lines):
        return None
    due = [(l["expiresAt"], "expires") for l in lines if l["expiresAt"]] + \
          [(l["revertsAt"], "reverts") for l in lines if l["needsPerson"] and l["revertsAt"]
           and l["command"] == "isolate_host"]
    deadline, kind = min(due) if due else (None, None)
    started = _aware((incident or {}).get("startedAt")) or min(
        (_aware(r.get("createdAt")) for r in rows if _aware(r.get("createdAt"))), default=None)
    return {"id": incident_id, "host": host, "startedAt": _iso(started),
            "alertCount": int((incident or {}).get("alertCount") or 0), "deadlineAt": deadline,
            "deadlineKind": kind, "actions": lines[:LINE_CAP], "actionCount": len(lines)}


# ---------------------------------------------------------------- the list

async def stopped_view(db, tenant_id: str) -> Optional[Dict[str, str]]:
    """{scope} when automatic actions are stopped (the browser then disables Approve and Confirm isolation).
    Anything unreadable counts as a stop, as in the gate."""
    try:
        if settings.stop_active(await settings.platform_stop(db)):
            return {"scope": "platform"}
        s = await settings.load(db, tenant_id)
        return {"scope": "tenant"} if (not s.readable or settings.stop_active(s.stop)) else None
    except Exception as exc:
        logger.error("autonomous_ops: stop state unreadable for the cards, showing a stop: %s", exc)
        return {"scope": "tenant"}


async def list_cards(db, tenant_id: str, *, offset: int = 0, limit: int = 10, can_act: bool = False,
                     staff: bool = False, now: Optional[datetime] = None) -> Dict[str, Any]:
    """One page of incident cards for the organization, with ``total``, the stop state and ``serverNow`` (the
    clock the deadlines were read against, ISO UTC: the browser compares with it, not its own, WR-27).
    ``can_act`` is True for a person holding control:autonomous_ops in an interactive session; it only sets
    the line flags."""
    now = _now(now)
    clock = now.isoformat(timespec="milliseconds")
    actions = raw(db).autonomy_actions
    seeds = actions.find({"tenantId": tenant_id, "kind": {"$ne": "control"},
                          "reason.inputs.incidentId": {"$type": "string"}, "$or": _waiting_filter(now)},
                         {"_id": 0, "reason.inputs.incidentId": 1}).sort([("createdAt", -1), ("id", -1)]).limit(SEED_CAP)
    ids = list(dict.fromkeys([_inputs(r)["incidentId"] async for r in seeds]))
    stopped = await stopped_view(db, tenant_id)
    if not ids:
        return {"items": [], "total": 0, "offset": offset, "limit": limit, "stopped": stopped, "serverNow": clock}
    rows = [ledger._normalize(r) async for r in actions.find(
        {"tenantId": tenant_id, "kind": {"$ne": "control"}, "reason.inputs.incidentId": {"$in": ids}},
        {"_id": 0}).sort([("createdAt", -1), ("id", -1)]).limit(ROW_CAP)]
    docs = {d["id"]: ledger._normalize(d) async for d in raw(db).autonomy_incidents.find(
        {"tenantId": tenant_id, "id": {"$in": ids}}, {"_id": 0})}
    agent_ids = sorted({str(d["agentId"]) for d in docs.values() if d.get("agentId")}
                       | {str(r["targets"][0]) for r in rows if r.get("targets")})
    hosts = {a["id"]: a["hostname"] async for a in raw(db).agents.find(
        {"tenantId": tenant_id, "id": {"$in": agent_ids}}, {"_id": 0, "id": 1, "hostname": 1}) if a.get("hostname")}
    by_incident: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        by_incident.setdefault(_inputs(row)["incidentId"], []).append(row)
    cards = [c for i in ids if (c := _card(i, by_incident.get(i, []), docs.get(i), hosts, can_act=can_act,
                                           staff=staff, now=now)) is not None]
    cards.sort(key=lambda c: c["startedAt"] or "", reverse=True)               # ties: the newer incident first
    cards.sort(key=lambda c: c["deadlineAt"] or "9999")                         # soonest deadline first
    return {"items": cards[offset:offset + limit], "total": len(cards), "offset": offset, "limit": limit,
            "stopped": stopped, "serverNow": clock}
