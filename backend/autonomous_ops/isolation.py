"""Isolation after it is done (Phase 83, plan 83-18, RESP-05, D-15): keeping it, telling the agent, noticing it ended.

An isolated computer returns to the network by itself 4 hours after the isolation unless a person confirms it. The
agent holds that timer (it works with no network). This module is the platform's side of it:

* ``confirm`` is the one new decision: a person with control access keeps the computer isolated. One compare-and-set
  on the ledger row (``ledger.mark_isolation_confirmed``), so two clicks give one winner and one ``already_handled``;
  refused during a stop, at or after the revert time, and for a row that is not an isolation.
* ``confirmed_ids`` lists, for one agent, the isolation ids a person confirmed. The heartbeat reply carries them as
  ``isolationConfirmed`` until the row ends; the agent confirms idempotently and cancels its revert. The id is the
  isolate instruction's own task id (the row's first instruction id), which the agent uses as the isolation id.
* ``run`` is a sweep stage. It moves an unconfirmed isolate row to ``rolled_back`` with reason ``auto_reverted`` once
  its revert time has passed AND the agent reports (``meta.response_state``) that it holds no isolation. An agent that
  has not reported yet, or whose state could not be read, leaves the row as it is. While the agent still reports the
  isolation active, the row's revert time is pulled in to the agent's own figure (``revert_in_seconds`` from its last
  heartbeat), never pushed out, so a confirm can't be accepted for time the agent no longer has.

A confirmed row is never touched by ``run``. Nothing here dispatches an instruction: undoing an isolation is the
ordinary Undo of the Activity row (restore_host with the same isolation id, ``approvals.undo``).

Raw Mongo handle with an explicit tenantId; the ambient tenant ContextVar is never used.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from . import gate, ledger, response_messages as rm
from .scope import raw

logger = logging.getLogger(__name__)

MAX_IDS = 5                         # the heartbeat reply stays small
PULL_IN_AFTER = timedelta(seconds=5)       # a smaller correction is not worth a write
_LIVE = ("executed", "verified")


def _now(now: Optional[datetime]) -> datetime:
    now = now or datetime.now(timezone.utc)
    now = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)       # BSON datetimes are milliseconds


def _aware(value: Any) -> Optional[datetime]:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------- the decision

async def confirm(db, tenant_id: str, action_id: str, actor: Dict[str, Any], *,
                  now: Optional[datetime] = None) -> Dict[str, Any]:
    """Keep an isolated computer isolated. Status: confirmed (plus ``action``), not_found, stopped,
    already_handled, refused (plus ``reason``: not_isolated, revert_passed). The route turns every status
    except ``confirmed`` into a 409 (404 for not_found)."""
    now = _now(now)
    row = await ledger.get(db, tenant_id, action_id)
    if row is None:
        return {"status": "not_found"}
    if await gate._stopped(db, tenant_id):          # D-12: a stop freezes every approval-like decision; an unreadable one counts
        return {"status": "stopped"}
    refusal = _not_isolation(row)
    if refusal:
        return {"status": "refused", "reason": refusal}
    won = await ledger.mark_isolation_confirmed(db, tenant_id, action_id, actor, now)
    if won is not None:
        return {"status": "confirmed", "action": won}
    latest = await ledger.get(db, tenant_id, action_id) or row
    refusal = _not_isolation(latest)
    if refusal:
        return {"status": "refused", "reason": refusal}
    iso = latest.get("isolation") if isinstance(latest.get("isolation"), dict) else {}
    if iso.get("confirmedAt"):
        return {"status": "already_handled"}
    reverts = _aware(iso.get("revertsAt"))
    if reverts is None:
        return {"status": "refused", "reason": "not_isolated"}
    if reverts <= now:
        return {"status": "refused", "reason": "revert_passed"}
    return {"status": "already_handled"}            # lost a race that is not visible any more


def _not_isolation(row: Dict[str, Any]) -> Optional[str]:
    """not_isolated when the row is not an isolation that is in place; revert_passed when it already returned."""
    if row.get("command") != "isolate_host" or row.get("dispatcher") != "security_response":
        return "not_isolated"
    if row.get("state") in _LIVE:
        return None
    if row.get("state") == "rolled_back" and row.get("reasonCode") == "auto_reverted":
        return "revert_passed"
    return "not_isolated"


# ---------------------------------------------------------------- what the agent is told

async def confirmed_ids(db, tenant_id: str, agent_id: str, now: Optional[datetime] = None) -> List[str]:
    """The isolation ids a person confirmed for this agent that are still in place, newest first, at most
    ``MAX_IDS``. Only this tenant's rows aimed at this agent."""
    found = raw(db).autonomy_actions.find(
        {"tenantId": tenant_id, "command": "isolate_host", "dispatcher": "security_response", "targets": agent_id,
         "state": {"$in": list(_LIVE)}, "isolation.confirmedAt": {"$ne": None}},
        {"_id": 0, "instructionIds": 1}).sort([("updatedAt", -1), ("id", -1)]).limit(MAX_IDS)
    ids = []
    async for row in found:
        first = (row.get("instructionIds") or [None])[0]
        if isinstance(first, str) and first:
            ids.append(first)
    return ids


# ---------------------------------------------------------------- noticing the end

def _reported(agent: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The agent's ``meta.response_state`` when it reported a readable one, else None (nothing can be said)."""
    meta = (agent or {}).get("meta")
    state = meta.get("response_state") if isinstance(meta, dict) else None
    if not isinstance(state, dict) or state.get("state_unreadable"):
        return None
    return state if "isolation" in state else None


async def _pull_in(db, tenant_id: str, row: Dict[str, Any], agent: Dict[str, Any], seconds: int) -> bool:
    """Set the row's revert time to the agent's own figure when that is earlier (never later)."""
    seen = _aware(agent.get("lastSeen"))
    current = _aware((row.get("isolation") or {}).get("revertsAt"))
    if seen is None or current is None:
        return False
    exact = (seen + timedelta(seconds=seconds)).replace(microsecond=0)
    if exact >= current - PULL_IN_AFTER:
        return False
    done = await raw(db).autonomy_actions.update_one(
        {"id": row["id"], "tenantId": tenant_id, "state": {"$in": list(_LIVE)}, "isolation.confirmedAt": None,
         "isolation.revertsAt": {"$gt": exact}}, {"$set": {"isolation.revertsAt": exact}})
    return done.modified_count == 1


async def run(db, tenant_id: str, tenant: Any, response: Any, now: datetime) -> Dict[str, int]:
    """The sweep stage (signature as in ``sweep``). Counts ``reverted`` (rows moved to rolled_back) and
    ``pulled_in`` (revert times corrected from an agent's report)."""
    counts = {"reverted": 0, "pulled_in": 0}
    rows = [ledger._normalize(r) async for r in raw(db).autonomy_actions.find(
        {"tenantId": tenant_id, "command": "isolate_host", "dispatcher": "security_response",
         "state": {"$in": list(_LIVE)}, "isolation.confirmedAt": None, "isolation.revertsAt": {"$ne": None}},
        {"_id": 0}).limit(200)]
    for row in rows:
        target = (row.get("targets") or [None])[0]
        agent = await raw(db).agents.find_one({"tenantId": tenant_id, "id": target},
                                              {"_id": 0, "lastSeen": 1, "meta.response_state": 1})
        state = _reported(agent)
        if state is None:
            continue                                      # the host has not said anything we can read: wait for it
        held = state.get("isolation")
        if isinstance(held, dict) and held.get("active"):
            left = held.get("revert_in_seconds")
            if isinstance(left, int) and not isinstance(left, bool) and left >= 0 and not held.get("confirmed"):
                counts["pulled_in"] += 1 if await _pull_in(db, tenant_id, row, agent, left) else 0
            continue
        if held is not None:
            continue                                      # not a shape we know: leave the row
        reverts = _aware((row.get("isolation") or {}).get("revertsAt"))
        if reverts is None or reverts > now:
            continue                                      # the host says nothing is held, but its time is not up
        moved = await ledger.transition(
            db, tenant_id, row["id"], _LIVE, "rolled_back", reasonCode="auto_reverted",
            reasonText=rm.REASON_TEXT["auto_reverted"],
            where={"isolation.confirmedAt": None, "isolation.revertsAt": {"$lte": now}})
        counts["reverted"] += 1 if moved else 0
    return counts
