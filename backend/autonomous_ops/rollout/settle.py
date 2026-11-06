"""Settling installs from what the agent actually reported (PTCH-01).

An agent answers an install instruction as "accepted" and posts the real outcome to the deployment
result route, which stores it on the host's own ``patch_deployment_jobs`` document under
``agentResults.<agent id with dots and dollars replaced>``. The reconciler cannot read that, so the
rollout controller does: every tick, before any new decision (also while a stop is on), it moves each
installing host to installed or failed from its own job, and ends the ledger row to match.

An instruction the delivery hook refused (it expired) or the stop cancelled, with no result, was never
installed: the row ends failed ``rollout_not_delivered`` and the host goes back to waiting for another
try.

Raw Mongo handle with an explicit tenantId only. Reads an instruction's status; never writes the queue.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .. import ledger, messages
from ..scope import raw
from . import store
from .installs import retry_fields

logger = logging.getLogger(__name__)

_NOT_DELIVERED = ("refused", "cancelled_by_stop", "cancelled")


def result_key(agent_id: str) -> str:
    """The key the result route files an agent's result under."""
    return agent_id.replace(".", "_").replace("$", "_")


def verdict_of(entry: Dict[str, Any], patch_ids: List[str]) -> Dict[str, Any]:
    """{"ok", "message", "rebootNeeded"} from one agent result. Installed only when every applicable id
    has a result with status success; anything else, including a missing id, is a failure."""
    results = [r for r in entry.get("results") or [] if isinstance(r, dict)]
    by_id = {str(r.get("patch_id")): r for r in results}
    bad = [p for p in patch_ids if str((by_id.get(p) or {}).get("status")).casefold() != "success"]
    reboot = bool(entry.get("rebootRequired")) or any(r.get("reboot_required") for r in results)
    if not bad and patch_ids:
        return {"ok": True, "message": None, "rebootNeeded": reboot}
    detail = next((str(by_id[p].get("message")) for p in bad if p in by_id and by_id[p].get("message")), None)
    message = detail or entry.get("error") or "The computer did not report success for every patch."
    return {"ok": False, "message": str(message)[:500], "rebootNeeded": reboot}


async def _instruction_status(db, tenant_id: str, instruction_id: Optional[str]) -> Optional[str]:
    if not instruction_id:
        return None
    doc = await raw(db).agent_instructions.find_one({"id": instruction_id, "tenantId": tenant_id},
                                                    {"_id": 0, "status": 1})
    status = (doc or {}).get("status")
    return status.strip().lower() if isinstance(status, str) else None


async def _settle_host(db, tenant_id: str, rollout: Dict[str, Any], host: Dict[str, Any], now: datetime) -> str:
    job = await raw(db).patch_deployment_jobs.find_one(
        {"id": host.get("installJobId"), "tenantId": tenant_id}, {"_id": 0, "agentResults": 1})
    entry = ((job or {}).get("agentResults") or {}).get(result_key(host["agentId"]))
    action_id = host.get("installActionId")
    if isinstance(entry, dict):
        verdict = verdict_of(entry, list(host.get("patchIds") or []))
        reported = store.parse_time(entry.get("reportedAt")) or store.aware(now)
        if verdict["ok"]:
            fields = {"state": "installed", "installReportedAt": reported, "rebootNeeded": verdict["rebootNeeded"]}
            to_state, code = "executed", "rollout_installed"
        else:
            fields = {"state": "failed", "installReportedAt": reported, "failureMessage": verdict["message"],
                      "rebootNeeded": verdict["rebootNeeded"]}
            to_state, code = "failed", "rollout_install_failed"
        if action_id:
            await ledger.transition(db, tenant_id, action_id, ("dispatching",), to_state, reasonCode=code,
                                    reasonText=messages.REASON_TEXT[code],
                                    result={"jobId": host.get("installJobId"), "agentStatus": entry.get("status")})
        await store.set_host(db, tenant_id, rollout["id"], host["agentId"], fields)
        return fields["state"]
    status = await _instruction_status(db, tenant_id, host.get("installInstructionId"))
    if status in _NOT_DELIVERED:
        if action_id:
            await ledger.transition(db, tenant_id, action_id, ("dispatching",), "failed",
                                    reasonCode="rollout_not_delivered",
                                    reasonText=messages.REASON_TEXT["rollout_not_delivered"])
        fields = retry_fields(host, int(host.get("attempt") or 1))
        await store.set_host(db, tenant_id, rollout["id"], host["agentId"], fields)
        return fields["state"]
    return "installing"


async def settle(db, tenant_id: str, rollout: Dict[str, Any], now: datetime) -> Dict[str, int]:
    """Settle every installing host of the rollout. Returns counts by new state. A failure on one host is
    logged and does not stop the others."""
    counts: Dict[str, int] = {}
    for host in await store.host_docs(db, tenant_id, rollout["id"]):
        if host.get("state") != "installing":
            continue
        try:
            new_state = await _settle_host(db, tenant_id, rollout, host, now)
        except Exception as exc:
            logger.error("autonomous_ops: rollout %s could not settle host %s: %s", rollout["id"], host["agentId"], exc)
            continue
        counts[new_state] = counts.get(new_state, 0) + 1
    return counts
