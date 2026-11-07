"""Rollout approval cards for Needs your decision (Phase 84, plan 84-10, PTCH-06, D-07, D-08).

A card is one ring of one rollout that has at least one line waiting for a person, or a line decided a moment ago
(so the result text can be shown for one poll). A line is the set of that ring's approval rows that share
``reason.inputs`` {rolloutId, ring, line} (``lines.py``): an Install line, a Reboot line (raised only after the ring's
installs settled, only for computers that need a restart) and a Revert restart line. Every line carries its own
``canApprove`` and ``canDeny``, worked out here from the caller's rights and the stop, so the browser never infers
a permission. A line is decided as a whole through ``lines.approve_line`` / ``deny_line`` (84-10 routes); there is no
approve-all.

Sentences come from ``messages`` (nothing is composed here beyond filling a template). A rollout that halted keeps
no open line (the halt closes them), so a denied or expired line is shown as a result only. A decided line stays on
its card for ``SETTLED_STAY`` (about two polls of the section), then the card leaves. Cards sort by soonest expiry,
ties by rollout start, newest first.

Raw Mongo handle with an explicit tenantId on every read; nothing here writes.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from .. import incident_views
from ..scope import raw
from . import DEFAULT_FAIL_PCT, DISPATCHER_NAME, LINES, messages as rm, store, windows as windows_mod

logger = logging.getLogger(__name__)

SETTLED_STAY = timedelta(seconds=60)
ROW_CAP = 2000                                    # rows read for one page
COMPUTER_NAMES = 10                               # names a line lists
PATCH_IDS_SHOWN = 3
INSTALL, REBOOT, REVERT_REBOOT = LINES
_RULES = [f"rollout:{line}" for line in LINES] + ["rollout:canary_install"]       # a held canary row is an Install row
_OPEN_STATES = ["awaiting_approval", "suggested"]      # a person has to decide either (KD-84-G1)
_ENDED_BY_ROLLOUT = ("rollout_closed", "rollout_halted", "rollout_not_delivered")   # not a person's decision
_DECIDED = ("approved", "dispatching", "executed", "verified", "failed", "undone", "rolled_back")
EXCLUDED_HOSTS = ("not_reached", "left_out")


def _now(now: Optional[datetime]) -> datetime:
    now = now or datetime.now(timezone.utc)
    now = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _inputs(row: Dict[str, Any]) -> Dict[str, Any]:
    return _dict(_dict(row.get("reason")).get("inputs"))


def _iso(value: Any) -> Optional[str]:
    moment = store.parse_time(value)
    return moment.isoformat() if moment else None


def _approver(row: Dict[str, Any]) -> str:
    who = _dict(_dict(row.get("approval")).get("approver"))
    return str(who.get("display") or who.get("name") or who.get("username") or "a person")


def _target(row: Dict[str, Any]) -> Optional[str]:
    targets = row.get("targets") or []
    return str(targets[0]) if targets else None


# ---------------------------------------------------------------- what is open, what was decided a moment ago

def _is_open(row: Dict[str, Any], now: datetime) -> bool:
    expires = store.parse_time(_dict(row.get("approval")).get("expiresAt"))
    return row.get("state") in _OPEN_STATES and expires is not None and expires > now


def _settled_at(row: Dict[str, Any]) -> Optional[datetime]:
    """When a person (or the 24 hours) decided the row, else None."""
    if row.get("reasonCode") in _ENDED_BY_ROLLOUT:
        return None
    state = row.get("state")
    if state == "denied" or state in _DECIDED:
        return store.parse_time(_dict(row.get("approval")).get("decidedAt"))
    if state == "expired":
        return store.parse_time(row.get("finishedAt"))
    return None


def _recent(row: Dict[str, Any], now: datetime) -> bool:
    moment = _settled_at(row)
    return moment is not None and now - SETTLED_STAY <= moment <= now + SETTLED_STAY


async def _pairs(db, tenant_id: str, now: datetime) -> List[Tuple[str, int]]:
    """The (rollout id, ring) pairs with an open row or one decided a moment ago, in a stable order."""
    since = now - SETTLED_STAY
    flt = {"tenantId": tenant_id, "dispatcher": DISPATCHER_NAME, "reason.ruleId": {"$in": _RULES},
           "reasonCode": {"$nin": list(_ENDED_BY_ROLLOUT)},
           "$or": [{"state": {"$in": _OPEN_STATES}, "approval.expiresAt": {"$gt": now}},
                   {"state": {"$in": ["denied", *_DECIDED]}, "approval.decidedAt": {"$gte": since}},
                   {"state": "expired", "finishedAt": {"$gte": since}}]}
    found = raw(db).autonomy_actions.find(flt, {"_id": 0, "reason.inputs.rolloutId": 1, "reason.inputs.ring": 1}) \
        .sort([("createdAt", -1), ("id", -1)]).limit(ROW_CAP)
    pairs: List[Tuple[str, int]] = []
    async for row in found:
        inputs = _inputs(row)
        ring = inputs.get("ring")
        if isinstance(inputs.get("rolloutId"), str) and isinstance(ring, int) and not isinstance(ring, bool):
            pairs.append((inputs["rolloutId"], ring))
    return list(dict.fromkeys(pairs))


# ---------------------------------------------------------------- the window clause

class _Window:
    """The tenant's window as the cards read it: the zone, the open occurrence now and the next one."""

    def __init__(self, tenant_windows: windows_mod.TenantWindows, now: datetime):
        self.zone = tenant_windows.zone if tenant_windows.readable else windows_mod.DEFAULT_ZONE
        self.open = tenant_windows.open_at(now)
        self.next = windows_mod.next_open(tenant_windows.windows, tenant_windows.zone, now) \
            if tenant_windows.readable and tenant_windows.windows else None

    def clause(self) -> str:
        if self.open is not None:
            return rm.fill(rm.CARD["window_clause"]["open"], closes=windows_mod.clock_text(self.open[1], self.zone))
        if self.next is not None:
            return rm.fill(rm.CARD["window_clause"]["next"], opens=windows_mod.when_text(self.next[0], self.zone))
        return ""

    def opens_text(self) -> Optional[str]:
        return windows_mod.when_text(self.next[0], self.zone) if self.next is not None else None


# ---------------------------------------------------------------- one line

def _patch_ids(rows: List[Dict[str, Any]]) -> List[str]:
    ids: List[str] = []
    for row in rows:
        for patch in _inputs(row).get("patchIds") or _dict(row.get("params")).get("patch_ids") or []:
            if isinstance(patch, str) and patch not in ids:
                ids.append(patch)
    return ids


def _target_text(ids: List[str]) -> str:
    shown = ", ".join(ids[:PATCH_IDS_SHOWN])
    return f"{shown} +{len(ids) - PATCH_IDS_SHOWN} more" if len(ids) > PATCH_IDS_SHOWN else shown


def _label(line: str, ids: List[str], computers: int) -> str:
    return rm.fill(rm.CARD["labels"][line], patches=rm.plural(len(ids), "patch", "patches"),
                   computers=rm.plural(computers, "computer", "computers"))


def _why(line: str, ring: int, ring_defs: List[Dict[str, Any]], ids: List[str], computers: int,
         rows: List[Dict[str, Any]], zone: str) -> str:
    plural = rm.plural(computers, "computer", "computers")
    if line == REBOOT:
        return rm.fill(rm.CARD["why"]["reboot"], computers=plural)
    if line == REVERT_REBOOT:
        return rm.fill(rm.CARD["why"]["revert_reboot"], computers=plural)
    if ring == 0 and rows and all((r.get("reason") or {}).get("ruleId") == "rollout:canary_install" for r in rows):
        return str(rows[0].get("reasonText") or "")          # a canary row the gate held says why in its own words
    if ring == 0:
        return rm.fill(rm.CARD["why"]["install_not_reversible"], patch=", ".join(ids))
    previous = ring_defs[ring - 1] if 0 < ring <= len(ring_defs) else {}
    passed = store.parse_time(previous.get("passedAt"))
    if passed is None or not previous.get("name"):
        return str(rows[0].get("reasonText") or "")
    return rm.fill(rm.CARD["why"]["install"], previous=previous["name"], at=windows_mod.when_text(passed, zone),
                   ring=ring_defs[ring].get("name") or "")


def _what_happens(line: str, ring_def: Dict[str, Any], window: _Window) -> str:
    if line == INSTALL:
        return rm.fill(rm.CARD["what_happens"]["install"], window_clause=window.clause(),
                       limit=int(ring_def.get("failPct") if ring_def.get("failPct") is not None else DEFAULT_FAIL_PCT))
    opens = window.opens_text()
    if opens is None:
        return rm.CARD["what_happens"]["restart_no_window"]
    return rm.fill(rm.CARD["what_happens"]["restart"], opens=opens)


def _result(line: str, state: str, subject: List[Dict[str, Any]], ring_name: str, window: _Window) -> str:
    if state == "denied":
        return rm.fill(rm.CARD["settled"]["denied"], name=_approver(subject[0]), ring=ring_name)
    if state == "expired":
        return rm.fill(rm.CARD["settled"]["expired"], ring=ring_name)
    settled = rm.CARD["settled"]
    key = "approved_install" if line == INSTALL else "approved_restart"
    if any(r.get("state") == "approved" for r in subject):               # approved, not sent yet
        opens = None if window.open is not None else window.opens_text()
        if opens is None:
            return rm.LINE_RESULT["waiting_computer"]
        return rm.fill(settled[key], when=rm.fill(settled["when_window"], opens=opens))
    return rm.fill(settled[key], when=settled["when_now"])


def _line(line: str, rows: List[Dict[str, Any]], *, ring: int, ring_defs: List[Dict[str, Any]],
          names: Dict[str, str], window: _Window, can_approve: bool, can_deny: bool,
          now: datetime) -> Optional[Dict[str, Any]]:
    """The line as the browser shows it, or None when it has nothing to show (nothing open, nothing decided a
    moment ago)."""
    open_rows = [r for r in rows if _is_open(r, now)]
    if open_rows:
        state, subject = "pending", open_rows
    else:
        recent = [r for r in rows if _recent(r, now)]
        # A denial halts the rollout, so it outranks an expiry, which outranks an approval.
        state, subject = next(((s, [r for r in recent if r.get("state") in states]) for s, states in
                               (("denied", ("denied",)), ("expired", ("expired",)), ("approved", _DECIDED))
                               if any(r.get("state") in states for r in recent)), (None, []))
        if state is None:
            return None
    agent_ids = list(dict.fromkeys(a for a in (_target(r) for r in subject) if a))
    computers = sorted((names.get(a) or a for a in agent_ids), key=lambda n: (n.casefold(), n))
    ids = _patch_ids(subject) if line == INSTALL else []
    ring_def = ring_defs[ring] if 0 <= ring < len(ring_defs) else {}
    ring_name = str(ring_def.get("name") or "")
    expiry = min((e for e in (store.parse_time(_dict(r.get("approval")).get("expiresAt")) for r in subject) if e),
                 default=None) if state == "pending" else None
    return {
        "line": line, "state": state, "label": _label(line, ids, len(agent_ids)), "targetText": _target_text(ids),
        "why": _why(line, ring, ring_defs, ids, len(agent_ids), subject, window.zone),
        "whatHappens": _what_happens(line, ring_def, window),
        "computers": computers[:COMPUTER_NAMES], "computerTotal": len(agent_ids),
        "canApprove": bool(can_approve and state == "pending"), "canDeny": bool(can_deny and state == "pending"),
        "resultText": None if state == "pending" else _result(line, state, subject, ring_name, window),
        "expiresAt": _iso(expiry),
    }


# ---------------------------------------------------------------- one card

def _card(rollout: Dict[str, Any], ring: int, rows: List[Dict[str, Any]], hosts: List[Dict[str, Any]],
          window: _Window, *, can_approve: bool, can_deny: bool, now: datetime) -> Optional[Dict[str, Any]]:
    ring_defs = [r for r in rollout.get("rings") or [] if isinstance(r, dict)]
    names = {h["agentId"]: str(h.get("hostname") or h["agentId"]) for h in hosts if h.get("agentId")}
    in_ring = [h for h in hosts if h.get("ring") == ring and h.get("state") not in EXCLUDED_HOSTS]
    lines = []
    for line in LINES:
        built = _line(line, [r for r in rows if _inputs(r).get("line") == line], ring=ring, ring_defs=ring_defs,
                      names=names, window=window, can_approve=can_approve, can_deny=can_deny, now=now)
        if built is not None:
            lines.append(built)
    if not lines:
        return None
    ring_name = str(ring_defs[ring].get("name") or "") if 0 <= ring < len(ring_defs) else ""
    deadline = min((l["expiresAt"] for l in lines if l["expiresAt"]), default=None)
    return {
        "kind": "rollout", "rolloutId": rollout["id"], "ring": str(ring),
        "anchorId": f"approval-rollout-{rollout['id']}-{ring}", "name": str(rollout.get("name") or ""),
        "subtitle": rm.fill(rm.CARD["ring_subtitle"], i=ring + 1, r=len(ring_defs), ring=ring_name,
                            computers=rm.plural(len(in_ring), "computer", "computers")),
        "expiresAt": deadline, "lines": lines, "startedAt": _iso(rollout.get("createdAt")),
    }


# ---------------------------------------------------------------- the list

async def list_cards(db, tenant_id: str, caller, *, offset: int = 0, limit: int = 10,
                     now: Optional[datetime] = None) -> Dict[str, Any]:
    """One page of rollout ring cards for the organization, with ``total``, the stop state, ``countText`` (the
    section's ``{k} rollout rings``) and ``serverNow`` (the clock the deadlines were read against). ``caller`` is an
    ``autonomous_ops.views.Caller``: a line may be decided by a person holding control:autonomous_ops in a signed-in
    session, and Approve (not Deny) is off during a stop."""
    now = _now(now)
    clock = now.isoformat(timespec="milliseconds")
    stopped = await incident_views.stopped_view(db, tenant_id)
    can_act = bool(caller.can_control and caller.interactive)
    page: Dict[str, Any] = {"items": [], "total": 0, "offset": offset, "limit": limit, "stopped": stopped,
                            "serverNow": clock, "countText": ""}
    pairs = await _pairs(db, tenant_id, now)
    if not pairs:
        return page
    rollout_ids = sorted({p[0] for p in pairs})
    rollouts = {d["id"]: d async for d in (store.normalise(doc) async for doc in store.rollouts(db).find(
        {"tenantId": tenant_id, "id": {"$in": rollout_ids}}, {"_id": 0}))}
    rows_found = raw(db).autonomy_actions.find(
        {"tenantId": tenant_id, "dispatcher": DISPATCHER_NAME, "reason.ruleId": {"$in": _RULES},
         "reason.inputs.rolloutId": {"$in": rollout_ids}}, {"_id": 0}).sort([("createdAt", 1), ("id", 1)]).limit(ROW_CAP)
    by_pair: Dict[Tuple[str, int], List[Dict[str, Any]]] = {}
    async for row in rows_found:
        inputs = _inputs(row)
        by_pair.setdefault((inputs.get("rolloutId"), inputs.get("ring")), []).append(store.normalise(row))
    window = _Window(await windows_mod.load(db, tenant_id), now)
    hosts = {rid: await store.host_docs(db, tenant_id, rid) for rid in rollout_ids if rid in rollouts}
    cards = [c for rid, ring in pairs if rid in rollouts
             and (c := _card(rollouts[rid], ring, by_pair.get((rid, ring), []), hosts[rid], window,
                             can_approve=can_act and stopped is None, can_deny=can_act, now=now)) is not None]
    cards.sort(key=lambda c: c["startedAt"] or "", reverse=True)               # ties: the newer rollout first
    cards.sort(key=lambda c: c["expiresAt"] or "9999")                          # soonest expiry first
    for card in cards:
        card.pop("startedAt", None)
    page.update(items=cards[offset:offset + limit], total=len(cards),
                countText=rm.plural(len(cards), "rollout ring", "rollout rings") if cards else "")
    return page
