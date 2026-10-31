"""The Autonomous Ops reconciler (GATE-11, D-13, D-16).

One background loop, one runner at a time (``distributed_lock.lock_with_renewal`` on
``autonomous_ops_reconciler``; a tick stops between tenants when the lock reports lost). Each
tick, per tenant in sorted tenantId order:

1. expires every overdue approval card (also while a stop is on, D-13);
2. maps rows still ``dispatching`` to the outcome of their latest instruction:
   completed / success -> ``executed`` (a ``security_response`` row then goes straight on to
   ``verified`` or ``failed`` from the agent's own verify result, see ``verify``); failed / refused -> ``failed``; an instruction nobody
   picked up within ``AUTONOMOUS_OPS_STUCK_DISPATCH_MIN`` (or no instruction at all) -> ``failed``
   with reason ``not_delivered``; an instruction an agent picked up (sent, delivered or any other
   status that is not pending / queued / a final outcome) that reports nothing within
   ``AUTONOMOUS_OPS_NO_RESULT_MIN`` (default 1440, never shorter than the not-delivered bound)
   -> ``failed`` with reason ``no_result``;
3. asks the circuit breaker to look at the tenant when any of its rows changed.

A failure for one tenant is logged and does not stop the others. Each tenant is processed inside
``scope.tenant_scope`` and the ContextVar is back to None after every tick. All reads and writes
use the raw handle with an explicit tenantId. The loop never calls ``breaker.restore``: nothing
time-driven re-arms a tripped breaker (D-18).
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Callable, Dict, Optional

from . import OPEN_STATES, approvals, breaker, ledger, messages, scope, verify
from .scope import raw

logger = logging.getLogger(__name__)

LOCK_NAME = "autonomous_ops_reconciler"
LOCK_TTL_SECONDS = 120
LOCK_RENEW_EVERY = 30
_DEFAULT_INTERVAL_SEC = 60
_DEFAULT_STUCK_MIN = 30
_DEFAULT_NO_RESULT_MIN = 1440

# Instruction / response-task statuses (compared case-insensitively). The agent result endpoint
# stores SUCCESS / FAILURE or the agent's own word upper-cased; response tasks use "executed".
_SUCCESS = frozenset({"completed", "success", "executed", "done"})
_FAILURE = frozenset({"failed", "failure", "refused", "error", "rejected"})
_UNDELIVERED = frozenset({"pending", "queued"})


def _env_number(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, default))
        return value if value > 0 else default
    except (TypeError, ValueError):
        return default


def _interval() -> float:
    return _env_number("AUTONOMOUS_OPS_RECONCILE_INTERVAL_SEC", _DEFAULT_INTERVAL_SEC)


def _stuck_after() -> timedelta:
    return timedelta(minutes=_env_number("AUTONOMOUS_OPS_STUCK_DISPATCH_MIN", _DEFAULT_STUCK_MIN))


def _no_result_after() -> timedelta:
    """How long a picked-up instruction may stay silent; never shorter than the not-delivered bound."""
    return max(timedelta(minutes=_env_number("AUTONOMOUS_OPS_NO_RESULT_MIN", _DEFAULT_NO_RESULT_MIN)),
               _stuck_after())


def _now(now: Optional[datetime]) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)


async def _latest_status(db, tenant_id: str, instruction_id: str) -> Optional[str]:
    """The lower-cased status of an instruction or response task of this tenant, else None."""
    handle = raw(db)
    doc = await handle.agent_instructions.find_one({"id": instruction_id, "tenantId": tenant_id},
                                                   {"_id": 0, "status": 1})
    if doc is None:
        doc = await handle.response_tasks.find_one({"task_id": instruction_id, "tenantId": tenant_id},
                                                   {"_id": 0, "status": 1})
    status = (doc or {}).get("status")
    return status.strip().lower() if isinstance(status, str) else None


async def _instruction(db, tenant_id: str, instruction_id: str):
    """The tenant's instruction document (status and stored result), else None."""
    return await raw(db).agent_instructions.find_one({"id": instruction_id, "tenantId": tenant_id},
                                                     {"_id": 0, "status": 1, "result": 1})


async def _reconcile_dispatches(db, tenant_id: str, now: datetime) -> Dict[str, int]:
    """Map this tenant's dispatching (and stuck approved) rows to their outcome."""
    done = {"executed": 0, "failed": 0}
    stuck_before = now - _stuck_after()
    no_result_before = now - _no_result_after()
    rows = [r async for r in raw(db).autonomy_actions.find(
        {"tenantId": tenant_id, "state": {"$in": ["approved", "dispatching"]}}, {"_id": 0})]
    for row in sorted(rows, key=lambda r: (str(r.get("createdAt")), r.get("id", ""))):
        updated = row.get("updatedAt") or row.get("createdAt")
        if isinstance(updated, datetime) and updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        old = isinstance(updated, datetime) and updated <= stuck_before
        ids = row.get("instructionIds") or []
        status = await _latest_status(db, tenant_id, ids[-1]) if ids and row["state"] == "dispatching" else None
        if status in _SUCCESS:
            moved = await ledger.transition(db, tenant_id, row["id"], ("dispatching",), "executed",
                                            result={"instructionId": ids[-1], "instructionStatus": status})
            done["executed"] += 1 if moved else 0
            if moved and moved.get("dispatcher") == "security_response":
                # The agent's own verify result decides verified / failed; nothing is re-scanned or undone (RESP-06).
                settled = await verify.settle(db, tenant_id, moved, await _instruction(db, tenant_id, ids[-1]), now=now)
                done["failed"] += 1 if settled == "failed" else 0
        elif status in _FAILURE:
            moved = await ledger.transition(
                db, tenant_id, row["id"], ("dispatching",), "failed", reasonCode="agent_failed",
                reasonText=messages.REASON_TEXT["agent_failed"],
                result={"instructionId": ids[-1], "instructionStatus": status})
            done["failed"] += 1 if moved else 0
        elif old and (status is None or status in _UNDELIVERED):
            moved = await ledger.transition(
                db, tenant_id, row["id"], ("approved", "dispatching"), "failed", reasonCode="not_delivered",
                reasonText=messages.REASON_TEXT["not_delivered"],
                where={"updatedAt": {"$lte": stuck_before}})
            done["failed"] += 1 if moved else 0
        elif (status and status not in _UNDELIVERED and isinstance(updated, datetime)
              and updated <= no_result_before):
            moved = await ledger.transition(
                db, tenant_id, row["id"], ("dispatching",), "failed", reasonCode="no_result",
                reasonText=messages.REASON_TEXT["no_result"],
                result={"instructionId": ids[-1], "instructionStatus": status},
                where={"updatedAt": {"$lte": no_result_before}})
            done["failed"] += 1 if moved else 0
    return done


async def tick(db, *, now: Optional[datetime] = None,
               lost: Optional[Callable[[], bool]] = None) -> Dict[str, int]:
    """One reconciliation pass. Returns counts {expired, executed, failed, tripped}. ``lost`` is
    polled between tenants; when it returns True the pass stops (the lock was lost)."""
    now = _now(now)
    counts = {"expired": 0, "executed": 0, "failed": 0, "tripped": 0}
    tenants = sorted(t for t in await raw(db).autonomy_actions.distinct(
        "tenantId", {"state": {"$in": list(OPEN_STATES)}}) if isinstance(t, str) and t)
    for tenant_id in tenants:
        if lost is not None and lost():
            logger.warning("autonomous_ops: reconciler lost its lock, stopping this pass")
            break
        try:
            with scope.tenant_scope(tenant_id):
                counts["expired"] += await approvals.expire_due(db, now=now, tenant_id=tenant_id)
                moved = await _reconcile_dispatches(db, tenant_id, now)
                counts["executed"] += moved["executed"]
                counts["failed"] += moved["failed"]
                if moved["executed"] or moved["failed"]:
                    counts["tripped"] += 1 if await breaker.evaluate(db, tenant_id, now=now) else 0
        except Exception as exc:
            logger.error("autonomous_ops: reconciler failed for tenant %s: %s", tenant_id, exc)
    return counts


async def run_once(db, *, now: Optional[datetime] = None) -> Optional[Dict[str, int]]:
    """One tick under the single-runner lock; None when another runner holds it."""
    import distributed_lock
    lock_db = SimpleNamespace(_db=raw(db))        # distributed_lock reads db._db
    async with distributed_lock.lock_with_renewal(lock_db, LOCK_NAME, ttl_seconds=LOCK_TTL_SECONDS,
                                                  renew_every=LOCK_RENEW_EVERY) as handle:
        if not handle.acquired:
            return None
        return await tick(db, now=now, lost=lambda: handle.lost)


async def reconciler_loop() -> None:
    """Run a tick every AUTONOMOUS_OPS_RECONCILE_INTERVAL_SEC. Keeps running during a stop (D-13)."""
    from database import get_database
    while True:
        try:
            counts = await run_once(get_database())
            if counts and any(counts.values()):
                logger.info("autonomous_ops: reconciler pass %s", counts)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("autonomous_ops: reconciler pass failed: %s", exc)
        await asyncio.sleep(_interval())
