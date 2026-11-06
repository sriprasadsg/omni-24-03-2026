"""How a rollout moves on and ends: pass a ring, complete the rollout (PTCH-01).

``advance`` marks the current ring passed and moves to the next; past the last ring it completes the
rollout. ``complete`` sets the status and releases every computer's claim so another rollout may take
them. ``halt`` stops the rollout at a ring (R11: a failed check, a denied or an expired approval): the
status moves from running to halted with one compare-and-set, every other open row of the rollout is closed
(``rollout_closed``), and a row whose instruction nobody has fetched yet is ended (``rollout_halted``) so
delivery refuses the instruction. A computer whose instruction was already sent keeps its row, and its
later result is still recorded. A halt claims nothing back from the computers: the rings that passed keep
their patches (reverting is plan 84-13).

Raw Mongo handle with an explicit tenantId only. Reads an instruction's status; never writes the queue.
"""
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from .. import ledger, messages
from ..scope import raw
from . import DISPATCHER_NAME, messages as rm, store

logger = logging.getLogger(__name__)


async def complete(db, tenant_id: str, rollout: Dict[str, Any], now: datetime) -> None:
    """The rollout is finished: status completed, claims released."""
    await store.set_rollout(db, tenant_id, rollout, {"status": "completed", "completedAt": now})
    await store.release(db, tenant_id, rollout["id"])


async def advance(db, tenant_id: str, rollout: Dict[str, Any], now: datetime) -> None:
    """The current ring passed: record it and move to the next ring, or complete the rollout after the last."""
    index = int(rollout.get("currentRing") or 0)
    await store.set_ring(db, tenant_id, rollout, index, {"state": "passed", "passedAt": now})
    if index + 1 >= len(rollout["rings"]):
        await complete(db, tenant_id, rollout, now)
        return
    await store.set_rollout(db, tenant_id, rollout, {"currentRing": index + 1})


async def _instruction_pending(db, tenant_id: str, instruction_id: Optional[str]) -> bool:
    """True when the row's newest instruction exists and is still waiting for the agent to fetch it."""
    if not instruction_id:
        return False
    doc = await raw(db).agent_instructions.find_one({"id": instruction_id, "tenantId": tenant_id}, {"_id": 0, "status": 1})
    return isinstance((doc or {}).get("status"), str) and doc["status"].strip().lower() == "pending"


async def _close_open_rows(db, tenant_id: str, rollout_id: str) -> int:
    """Every row of the rollout still waiting for a person or for the window is closed, so none can be
    approved or sent after the halt."""
    found = raw(db).autonomy_actions.find(
        {"tenantId": tenant_id, "dispatcher": DISPATCHER_NAME, "reason.inputs.rolloutId": rollout_id,
         "state": {"$in": ["awaiting_approval", "suggested", "approved"]}}, {"_id": 0, "id": 1})
    closed = 0
    for item in [r async for r in found]:
        done = await ledger.transition(db, tenant_id, item["id"], ("awaiting_approval", "suggested", "approved"),
                                       "expired", reasonCode="rollout_closed",
                                       reasonText=messages.REASON_TEXT["rollout_closed"])
        closed += 1 if done else 0
    return closed


async def _end_unfetched(db, tenant_id: str, rollout_id: str, ring: int) -> None:
    """A dispatching row of the ring whose instruction is still pending is failed ``rollout_halted``: delivery
    then refuses the instruction (its row is not dispatchable), and the computer is marked not reached."""
    found = raw(db).autonomy_actions.find(
        {"tenantId": tenant_id, "dispatcher": DISPATCHER_NAME, "reason.inputs.rolloutId": rollout_id,
         "reason.inputs.ring": ring, "state": "dispatching"}, {"_id": 0})
    for row in [r async for r in found]:
        if not await _instruction_pending(db, tenant_id, (row.get("instructionIds") or [None])[-1]):
            continue
        done = await ledger.transition(db, tenant_id, row["id"], ("dispatching",), "failed", reasonCode="rollout_halted",
                                       reasonText=messages.REASON_TEXT["rollout_halted"])
        if done:
            await store.set_host(db, tenant_id, rollout_id, (row.get("targets") or [None])[0],
                                 {"state": "not_reached", "waitReason": None})


async def halt(db, tenant_id: str, rollout: Dict[str, Any], ring: int, *, code: str, now: datetime,
               host: Optional[str] = None, facts: Optional[Dict[str, Any]] = None) -> bool:
    """Stop the rollout at ``ring``. Returns False when it was not running (someone halted it first).
    ``facts`` fill the reason sentence (``host`` as a name, ``f``, ``computers``, ``limit``)."""
    text = rm.fill(rm.HALT_REASON.get(code, ""), **{"host": host or "", **(facts or {})})
    reason = {"code": code, "ring": ring, "host": host, "text": text, "at": now}
    won = await store.rollouts(db).update_one(
        {"id": rollout["id"], "tenantId": tenant_id, "status": "running"},
        {"$set": {"status": "halted", "haltedAt": now, "haltReason": reason, f"rings.{ring}.state": "halted"}})
    if won.modified_count == 0:
        return False
    rollout.update({"status": "halted", "haltedAt": now, "haltReason": reason})
    rollout["rings"][ring]["state"] = "halted"
    await _close_open_rows(db, tenant_id, rollout["id"])
    await _end_unfetched(db, tenant_id, rollout["id"], ring)
    return True
