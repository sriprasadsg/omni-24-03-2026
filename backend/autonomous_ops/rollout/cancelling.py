"""A running rollout whose Cancel was requested ends once the work already on the computers settles (plan 84-28).

``lifecycle.cancel`` stamped ``cancelRequested`` {by, at}, closed the open rows and ended the instructions nobody had
fetched. From then on the controller calls ``tick`` instead of deciding anything: it runs no ring verdict, raises no
line, sends nothing, halts nothing and reverts nothing (D-16: hosts already patched keep their patches). ``tick``
ends the rollout through ``lifecycle.finish_cancel`` when no computer is installing or restarting any more, and at the
latest ``RESULT_DEADLINE`` after the request. A computer still in flight at that moment is marked failed with
``rollout_no_result`` (it did not answer in time), its row and job are closed, and nothing else happens to it.

Raw Mongo handle with an explicit tenantId only. Never writes the agent queue.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List

from .. import ledger, messages
from ..scope import raw
from . import DISPATCHER_NAME, inflight, lifecycle, store

logger = logging.getLogger(__name__)

IN_FLIGHT = ("installing", "restarting")        # a computer the cancel still waits for


async def _abandon(db, tenant_id: str, rollout_id: str, busy: List[Dict[str, Any]], now: datetime) -> None:
    """The computers still in flight at the bound did not answer: their rows and jobs close and they read failed."""
    text = messages.REASON_TEXT["rollout_no_result"]
    found = raw(db).autonomy_actions.find(
        {"tenantId": tenant_id, "dispatcher": DISPATCHER_NAME, "reason.inputs.rolloutId": rollout_id,
         "state": "dispatching", "targets": {"$in": [h["agentId"] for h in busy]}}, {"_id": 0})
    for item in [r async for r in found]:
        if await ledger.transition(db, tenant_id, item["id"], ("dispatching",), "failed", reasonCode="rollout_no_result",
                                   reasonText=text):
            await inflight.close_job(db, tenant_id, (item.get("params") or {}).get("job_id"), now, text)
    for h in busy:
        await store.set_host(db, tenant_id, rollout_id, h["agentId"], {
            "state": "failed", "failureCode": "rollout_no_result", "failureMessage": text, "waitReason": None})


async def _end_unsent(db, tenant_id: str, rollout_id: str) -> None:
    """A row still claimed for dispatch that never got an instruction (a restart row cannot be recovered by the install
    settle) is closed with the rollout, so it does not stay claimed for ever."""
    found = raw(db).autonomy_actions.find(
        {"tenantId": tenant_id, "dispatcher": DISPATCHER_NAME, "reason.inputs.rolloutId": rollout_id,
         "state": "dispatching", "instructionIds": {"$in": [None, []]}}, {"_id": 0, "id": 1})
    for item in [r async for r in found]:
        await ledger.transition(db, tenant_id, item["id"], ("dispatching",), "failed", reasonCode="rollout_closed",
                                reasonText=messages.REASON_TEXT["rollout_closed"])


async def tick(db, tenant_id: str, rollout: Dict[str, Any], now: datetime) -> bool:
    """One controller pass over a running rollout with ``cancelRequested``, after settle has read the results. True
    when the rollout ended cancelled now. Never raises: a fault is logged and the next pass tries again."""
    request = rollout.get("cancelRequested") if isinstance(rollout.get("cancelRequested"), dict) else {}
    try:
        busy = [h for h in await store.host_docs(db, tenant_id, rollout["id"]) if h.get("state") in IN_FLIGHT]
        asked = store.parse_time(request.get("at")) or store.aware(now)
        if busy and store.aware(now) < asked + inflight.RESULT_DEADLINE:
            return False
        if busy:
            await _abandon(db, tenant_id, rollout["id"], busy, now)
        await _end_unsent(db, tenant_id, rollout["id"])
        return await lifecycle.finish_cancel(db, tenant_id, rollout, request.get("by"), now, expect="running") is not None
    except Exception as exc:
        logger.error("autonomous_ops: rollout %s could not finish its cancel, trying again: %s", rollout.get("id"), exc)
        return False
