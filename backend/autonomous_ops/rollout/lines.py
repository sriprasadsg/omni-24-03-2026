"""Approval lines: everything in a rollout that is not an automatic canary install waits for a person (PTCH-06).

A ring step (an install, a restart, a revert restart) is one ledger row per computer, never one row for
many computers (planner decision OQ2, recorded in plan 84-03): each computer keeps its own patch list and
job, each revert is the plain undo of its own row, and Activity shows one row per computer. A *line* is the
set of one ring's rows that share ``reason.inputs`` {rolloutId, ring, line}. ``raise_line`` asks the gate
for one row per computer (``playbook_raise``, so each is a card in ``awaiting_approval``); ``approve_line``
and ``deny_line`` run ``approvals.approve`` / ``approvals.deny`` once per row, so every single-use,
expiry, re-validation and permission rule is the one the rest of Autonomous Ops already has. One line's
approval never approves another line, another ring or another rollout (PROH-84-04b): there is no
approve-all, and the rows are always found by rollout, ring and line together.

An approved row is sent by ``dispatcher`` (inside the window only). A denied line, or one nobody answered in
24 hours, halts the rollout at that ring; ``closed_line`` finds it and the controller halts.

Raw Mongo handle with an explicit tenantId only.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .. import approvals, gate
from ..scope import raw
from . import COMMAND_INSTALL, DISPATCHER_NAME, messages as rm, store
from . import dispatcher as _dispatcher  # noqa: F401  (importing registers the approvals dispatcher)

logger = logging.getLogger(__name__)

Entry = Tuple[Dict[str, Any], str, Dict[str, Any]]      # (host document, command, params)
_AUTOMATIC_RULE = "rollout:canary_install"
OPEN_ROW_STATES = ("awaiting_approval", "suggested")      # a person has to decide either one (KD-84-G1)


def _now(now: Optional[datetime]) -> datetime:
    now = now or datetime.now(timezone.utc)
    now = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


def _stamp(moment: Any) -> str:
    moment = store.parse_time(moment)
    return f"{moment:%Y-%m-%d %H:%M} UTC" if moment else ""


def install_entry(host: Dict[str, Any], patch_ids: Iterable[str]) -> Entry:
    """An install line entry: this computer's patches and the id of the job that will carry them. The job
    itself is made when the row is sent (``dispatcher.ensure_job``)."""
    return host, COMMAND_INSTALL, {"patch_ids": list(patch_ids), "job_id": uuid.uuid4().hex}


def _why(rollout: Dict[str, Any], ring: int, line: str, host: Dict[str, Any], ids: List[str]) -> str:
    """The sentence the card shows as its reason (UI-SPEC section 6)."""
    rings = rollout.get("rings") or []
    if line == "install" and ring == 0:
        return rm.fill(rm.ACTIVITY["not_reversible_why"], patch=", ".join(ids), host=host.get("hostname") or host["agentId"])
    if line == "install":
        previous = rings[ring - 1] if 0 < ring <= len(rings) else {}
        return rm.fill(rm.CARD["why"]["install"], previous=previous.get("name") or "The previous ring",
                       at=_stamp(previous.get("passedAt")), ring=(rings[ring].get("name") if ring < len(rings) else ""))
    key = "revert_reboot" if line == "revert_reboot" else "reboot"
    return rm.fill(rm.CARD["why"][key], computers=rm.plural(1, "computer", "computers"))


def _approval_filter(tenant_id: str, rollout_id: str, ring: int, line: str) -> Dict[str, Any]:
    rules = [f"rollout:{line}"] + ([_AUTOMATIC_RULE] if line == "install" else [])      # a held canary row is an install row
    return {"tenantId": tenant_id, "dispatcher": DISPATCHER_NAME, "reason.inputs.rolloutId": rollout_id,
            "reason.inputs.ring": ring, "reason.inputs.line": line, "reason.ruleId": {"$in": rules}}


async def line_rows(db, tenant_id: str, rollout_id: str, ring: int, line: str,
                    states: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
    """The approval rows of one line of one ring of one rollout, oldest first, optionally only in ``states``."""
    flt = _approval_filter(tenant_id, rollout_id, ring, line)
    if states is not None:
        flt["state"] = {"$in": list(states)}
    found = raw(db).autonomy_actions.find(flt, {"_id": 0}).sort([("createdAt", 1), ("id", 1)])
    return [r async for r in found]


def shadow_flag(rollout: Dict[str, Any]) -> Optional[bool]:
    """``master_shadow`` for ``gate.decide``: True for a rollout that was started as a simulation (81 D-02, research
    pitfall 5), so it stays one whatever the organization's shadow switch says later. None for a live rollout, which
    lets the gate read the deployment and organization switches as it does for everything else."""
    return True if rollout.get("shadow") else None


_SHADOW_STATE = {"install": "would_install", "reboot": "would_restart"}      # a revert restart changes no computer state


async def raise_line(db, tenant_id: str, rollout: Dict[str, Any], ring: int, line: str, entries: List[Entry],
                     now: datetime, *, master_shadow: Optional[bool] = None) -> Dict[str, int]:
    """Ask the gate for one approval row per entry. Returns counts of ``raised``, ``simulated`` and ``skipped``.
    The gate escalates every request to a card (``playbook_raise``); a simulation rollout, or an organization in
    shadow mode, records a ``shadow`` row and no card, and the computer reads ``would_install`` or ``would_restart``
    with its attempt counted, so the next real row after shadow is lifted is a new attempt with a new dedupe key.
    The caller must not call this while a stop is on (a stopped ``decide`` records a refused row each time)."""
    counts = {"raised": 0, "simulated": 0, "skipped": 0}
    if master_shadow is None:
        master_shadow = shadow_flag(rollout)
    for host, command, params in entries:
        ids = list(params.get("patch_ids") or [])
        agent_id = host["agentId"]
        attempt = int(host.get("attempt") or 0) + 1
        sequence = len((host.get("lineActionIds") or {}).get(line) or []) + 1
        request = gate.ActionRequest(
            tenant_id=tenant_id, kind="patching", origin="rollout", actions=[command], targets=[agent_id],
            params=params, playbook_raise=True, dispatcher=DISPATCHER_NAME,
            dedupe_key=f"{tenant_id}|{DISPATCHER_NAME}|{rollout['id']}|{ring}|{line}|{agent_id}|{attempt}|{sequence}",
            reason={"ruleId": f"rollout:{line}",
                    "inputs": {"rolloutId": rollout["id"], "ring": ring, "line": line, "attempt": attempt,
                               "patchIds": ids}},
            reason_text=_why(rollout, ring, line, host, ids))
        decision = await gate.decide(db, request, master_shadow=master_shadow, now=now)
        if not decision.recorded or not decision.action_id:
            counts["skipped"] += 1
            continue
        if decision.shadow:
            shown = _SHADOW_STATE.get(line)
            if shown:
                await store.set_host(db, tenant_id, rollout["id"], agent_id, {"state": shown, "attempt": attempt})
            counts["simulated"] += 1
            continue
        if decision.state not in OPEN_ROW_STATES:
            counts["skipped"] += 1           # the gate refused: nothing to wait for
            continue
        await track_line(db, tenant_id, rollout["id"], agent_id, line, decision.action_id, ids)
        counts["raised"] += 1
    return counts


async def track_line(db, tenant_id: str, rollout_id: str, agent_id: str, line: str, action_id: str,
                     patch_ids: Iterable[str]) -> None:
    """Remember an open approval row on its computer: its id under ``lineActionIds.<line>``, its patches in
    ``linePatchIds`` (so nothing asks for them twice), and the computer reads "waiting for approval". Used for
    every row a person has to decide, including a canary row the gate held (KD-84-G1)."""
    where = {"tenantId": tenant_id, "rolloutId": rollout_id, "agentId": agent_id}
    await store.hosts(db).update_one(
        where, {"$push": {f"lineActionIds.{line}": action_id}, "$addToSet": {"linePatchIds": {"$each": list(patch_ids)}}})
    await store.hosts(db).update_one({**where, "state": "waiting"}, {"$set": {"waitReason": "approval"}})


async def has_approved(db, tenant_id: str, rollout_id: str, ring: int) -> bool:
    """True when a person approved a row of the ring that has not been sent yet (it waits for the window)."""
    flt = {"tenantId": tenant_id, "dispatcher": DISPATCHER_NAME, "reason.inputs.rolloutId": rollout_id,
           "reason.inputs.ring": ring, "state": "approved"}
    return await raw(db).autonomy_actions.find_one(flt, {"_id": 1}) is not None


async def closed_line(db, tenant_id: str, rollout_id: str, ring: int, *, since: Any = None,
                      handled: Iterable[str] = ()) -> Optional[Dict[str, Any]]:
    """The first approval row of the ring that a person denied or that expired unanswered, as
    ``{"code": install_denied | restart_denied | approval_expired, "host": agent id}``, else None. A row the
    rollout itself closed (reasonCode ``rollout_closed``) is not a decision. Nor is a row that ran out while a stop was
    on (``since`` is when the stop began: nobody could approve then) or one the controller already offered again
    after such a stop (``handled`` holds those row ids)."""
    flt: Dict[str, Any] = {
        "tenantId": tenant_id, "dispatcher": DISPATCHER_NAME, "reason.inputs.rolloutId": rollout_id,
        "reason.inputs.ring": ring, "reason.ruleId": {"$in": ["rollout:install", _AUTOMATIC_RULE, "rollout:reboot", "rollout:revert_reboot"]},
        "state": {"$in": ["denied", "expired"]}, "reasonCode": {"$ne": "rollout_closed"}}
    if handled:
        flt["id"] = {"$nin": list(handled)}
    if store.parse_time(since) is not None:
        flt["$nor"] = [{"state": "expired", "finishedAt": {"$gte": store.parse_time(since)}}]
    found = raw(db).autonomy_actions.find(flt, {"_id": 0}).sort([("finishedAt", 1), ("id", 1)]).limit(1)
    for row in [r async for r in found]:
        line = (row.get("reason") or {}).get("inputs", {}).get("line")
        if row.get("state") == "expired":
            code = "approval_expired"
        else:
            code = "install_denied" if line == "install" else "restart_denied"
        return {"code": code, "host": (row.get("targets") or [None])[0]}
    return None


# ---------------------------------------------------------------- one click per line

def _result(status: str, *, when: Optional[str] = None, opens: Any = None, approved: int = 0,
            refused: Optional[List[Dict[str, str]]] = None, message: str = "") -> Dict[str, Any]:
    """The LineDecisionResult of services/patchRollouts/types.ts."""
    moment = store.parse_time(opens)
    return {"status": status, "when": when, "windowOpensAt": moment.isoformat() if moment else None,
            "approved": approved, "refused": refused or [], "message": message}


async def _running(db, tenant_id: str, rollout_id: str,
                   line: str = "") -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """(rollout, None) when it exists and is running (a halted rollout too, for its Revert restart line, and a
    completed one that is not closed yet, for the install offered to a computer that came back), else
    (None, the refusing result)."""
    rollout = await store.rollouts(db).find_one({"id": rollout_id, "tenantId": tenant_id},
                                                {"_id": 0, "id": 1, "status": 1, "rings": 1, "closedAt": 1})
    if rollout is None:
        return None, _result("refused", message=rm.LINE_RESULT["not_found"])
    status = rollout.get("status")
    open_tail = line == "install" and status == "completed" and not rollout.get("closedAt")    # a computer that came back (D-18)
    if status != "running" and not (line == "revert_reboot" and status == "halted") and not open_tail:
        return None, _result("refused", message=rm.LINE_RESULT["not_running"])
    return rollout, None


async def _hostname(db, tenant_id: str, rollout_id: str, agent_id: Any) -> str:
    doc = await store.hosts(db).find_one({"tenantId": tenant_id, "rolloutId": rollout_id, "agentId": agent_id},
                                         {"_id": 0, "hostname": 1})
    return str((doc or {}).get("hostname") or agent_id or "")


async def approve_line(db, tenant_id: str, rollout_id: str, ring: int, line: str, *, approver: Dict[str, Any],
                       now: Optional[datetime] = None) -> Dict[str, Any]:
    """Approve every awaiting row of one line of one ring, one ``approvals.approve`` per row, so one click is
    one approval per stage and a second click finds every row already handled. A row sent at once counts as
    ``now``; with the window closed (or the computer unable to take it yet) the rows stay approved and the
    answer is ``window``. A stop changes nothing."""
    now = _now(now)
    rollout, refusal = await _running(db, tenant_id, rollout_id, line)
    if rollout is None:
        return refusal
    if await gate._stopped(db, tenant_id):
        return _result("stopped", message=rm.LINE_RESULT["stopped"])
    awaiting = await line_rows(db, tenant_id, rollout_id, ring, line, OPEN_ROW_STATES)
    if not awaiting:
        if await line_rows(db, tenant_id, rollout_id, ring, line):
            return _result("already_handled", message=rm.LINE_RESULT["already_handled"])
        return _result("refused", message=rm.LINE_RESULT["nothing_open"])
    sent = deferred = expired = 0
    opens: Any = None
    refused: List[Dict[str, str]] = []
    for row in awaiting:
        answer = await approvals.approve(db, tenant_id, row["id"], approver=approver, now=now)
        status = answer.get("status")
        dispatch = answer.get("dispatch") or {}
        if status == "stopped":
            return _result("stopped", approved=sent + deferred, message=rm.LINE_RESULT["stopped"])
        if status == "dispatched" and dispatch.get("status") == "deferred":
            deferred += 1
            opens = opens or dispatch.get("windowOpensAt")
        elif status == "dispatched":
            sent += 1
        elif status == "expired":
            expired += 1
        elif status == "refused":
            refused.append({"hostname": await _hostname(db, tenant_id, rollout_id, (row.get("targets") or [None])[0]),
                            "reason": str(answer.get("reason") or "refused")})
    approved = sent + deferred
    if not approved:
        status = "expired" if expired else "refused" if refused else "already_handled"
        return _result(status, refused=refused, message=rm.LINE_RESULT["already_handled"])
    key = "approved_install" if line == "install" else "approved_restart"
    if deferred:
        when = rm.fill(rm.CARD["settled"]["when_window"], opens=_stamp(opens)) if opens else rm.LINE_RESULT["waiting_computer"]
        message = rm.fill(rm.CARD["settled"][key], when=when) if opens else rm.LINE_RESULT["waiting_computer"]
        return _result("approved", when="window", opens=opens, approved=approved, refused=refused, message=message)
    message = rm.fill(rm.CARD["settled"][key], when=rm.CARD["settled"]["when_now"])
    return _result("approved", when="now", approved=approved, refused=refused, message=message)


async def deny_line(db, tenant_id: str, rollout_id: str, ring: int, line: str, *, approver: Dict[str, Any],
                    reason: str = "") -> Dict[str, Any]:
    """Deny every awaiting row of one line of one ring, one ``approvals.deny`` per row. Writes nothing to an
    agent. The controller halts the rollout at the ring on its next pass."""
    rollout, refusal = await _running(db, tenant_id, rollout_id, line)
    if rollout is None:
        return refusal
    awaiting = await line_rows(db, tenant_id, rollout_id, ring, line, OPEN_ROW_STATES)
    if not awaiting:
        if await line_rows(db, tenant_id, rollout_id, ring, line):
            return _result("already_handled", message=rm.LINE_RESULT["already_handled"])
        return _result("refused", message=rm.LINE_RESULT["nothing_open"])
    denied = 0
    for row in awaiting:
        answer = await approvals.deny(db, tenant_id, row["id"], approver=approver, reason=reason)
        denied += 1 if answer.get("status") == "denied" else 0
    if not denied:
        return _result("already_handled", message=rm.LINE_RESULT["already_handled"])
    rings = rollout.get("rings") or []
    name = rings[ring].get("name") if 0 <= ring < len(rings) else ""
    who = approver.get("display") or approver.get("name") or approver.get("username") or "a person"
    return _result("denied", message=rm.fill(rm.CARD["settled"]["denied"], name=who, ring=name))
