"""The ``security_response`` dispatcher (Phase 83): one way a decided response action reaches an agent.

The sweep calls ``send`` for a row the gate recorded as ``dispatching``; an approval card of the same
dispatcher calls ``dispatcher`` through ``approvals`` once a person approved it. Both go through
``gate.execute``, the only writer of stamped instructions, so the stop check and the binding of the
instruction to what was decided apply on this path exactly as on every other.

For a block, the row also records when it began and when it will lift (``blockedFrom``,
``blockedUntil``) from the decided ``ttl_seconds``: the agent enforces the same expiry itself, so the
backend never has to send an unblock for it (and never does, see ``verify``).

A refused dispatch moves the row out of ``dispatching`` at once so it cannot hold its dedupe key open:
a stop that landed after the decision ends it ``cancelled_by_stop``; anything else ends it ``failed``
with ``dispatch_failed``.

Raw Mongo handle with an explicit tenantId; the ambient tenant ContextVar is never used.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from . import approvals, gate, ledger, messages
from .scope import raw

logger = logging.getLogger(__name__)

DISPATCHER_NAME = "security_response"


async def _stamp_block_window(db, row: Dict[str, Any]) -> None:
    ttl = (row.get("params") or {}).get("ttl_seconds")
    if isinstance(ttl, bool) or not isinstance(ttl, int) or ttl <= 0:
        return
    began = datetime.now(timezone.utc)
    began = began.replace(microsecond=began.microsecond // 1000 * 1000)
    try:
        await raw(db).autonomy_actions.update_one(
            {"id": row["id"], "tenantId": row["tenantId"]},
            {"$set": {"blockedFrom": began, "blockedUntil": began + timedelta(seconds=ttl)}})
    except Exception as exc:
        logger.error("autonomous_ops: block window for %s not recorded: %s", row.get("id"), exc)


async def send(db, row: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch one decided row to its first target. Returns gate.execute's answer
    ({status: queued, task_id} or {status: refused, reason}). Never raises for a refusal."""
    result = await gate.execute(db, row["tenantId"], row["id"], command=row.get("command"),
                                agent_id=(row.get("targets") or [None])[0], params=row.get("params") or {},
                                kind="action")
    if result.get("status") == "queued":
        if row.get("command") == "block_ip":
            await _stamp_block_window(db, row)
        return result
    reason = result.get("reason")
    if reason == "stopped":
        await ledger.transition(db, row["tenantId"], row["id"], ("approved", "dispatching"), "cancelled_by_stop",
                                reasonCode="platform_stop", reasonText=messages.REASON_TEXT["platform_stop"])
    else:
        await ledger.transition(db, row["tenantId"], row["id"], ("approved", "dispatching"), "failed",
                                reasonCode="dispatch_failed", reasonText=messages.REASON_TEXT["dispatch_failed"])
    return result


async def dispatcher(db, row: Dict[str, Any], approver: Dict[str, Any]) -> Dict[str, Any]:
    """The approvals dispatcher: the row is already ``approved``."""
    return await send(db, row)


approvals.register_dispatcher(DISPATCHER_NAME, dispatcher)
