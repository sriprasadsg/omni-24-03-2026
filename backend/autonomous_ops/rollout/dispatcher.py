"""The ``patch_rollout`` approvals dispatcher: an approved rollout row is sent only inside the window (PTCH-05).

A person approves a rollout card (``approvals.approve``, one compare-and-set per row) and the card's
dispatcher decides when it goes out. ``send`` answers ``deferred`` and leaves the row ``approved`` when the
window is closed or the computer cannot take the step right now; ``dispatch_approved`` is the controller's
way to send those rows when the window opens. At dispatch time, which can be days after the approval, the
host is checked again: the rollout is still running, the computer is still claimed, the tenant still has
the capability, the agent is online, reports the token the step needs and has no other patch job in
progress. A computer that fails a check is never sent anything.

A row is sent with ``gate.execute`` (the only writer of stamped instructions) and ``expires_at`` set to the
end of the window occurrence in force, so a late instruction is refused at delivery. Before that the row is
claimed with one compare-and-set to ``dispatching``, so a click and a tick that meet on one row write one
instruction, not two. Nothing here writes an agent queue.

Importing this module registers the dispatcher with ``approvals``; ``lines`` and ``controller`` import it,
so every process that approves or ticks has it.

Raw Mongo handle with an explicit tenantId only.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import agent_capabilities

from .. import agent_support, approvals, gate, ledger, messages
from ..scope import raw
from . import (CAPABILITY, COMMAND_INSTALL, COMMAND_UNDO, DISPATCHER_NAME, TOKEN_REBOOT, TOKEN_REVERSIBLE,
               TOKEN_REVERT_BY_JOB, reboots, store, windows as windows_mod)

logger = logging.getLogger(__name__)

_AGENT_FIELDS = {"_id": 0, "id": 1, "tenantId": 1, "status": 1, "lastSeen": 1, "platform": 1, "meta.response_actions": 1}


def _now(now: Optional[datetime]) -> datetime:
    now = now or datetime.now(timezone.utc)
    now = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)       # BSON datetimes are milliseconds


def required_token(row: Dict[str, Any]) -> Optional[str]:
    """The agent token the row's step needs: the restart token for a restart, the revert-by-job token for a
    revert, the reversibility token for an install that must be reversible, none for an approved install."""
    command = row.get("command")
    if command == "reboot_host":
        return TOKEN_REBOOT
    if command == COMMAND_UNDO:
        return TOKEN_REVERT_BY_JOB
    if command == COMMAND_INSTALL and (row.get("params") or {}).get("require_reversible"):
        return TOKEN_REVERSIBLE
    return None


async def ensure_job(db, tenant_id: str, rollout_id: str, agent_id: str, patch_ids, job_id: str, now: datetime) -> None:
    """The host's own patch job for an install, created once (a retried dispatch finds it again). It is made
    only when the row is about to be sent, so a card nobody approves leaves no job that looks in progress."""
    from patch_core_endpoints import new_patch_job
    job = new_patch_job(job_id, tenant_id, list(patch_ids), [agent_id], [agent_id], "Autonomous Ops", "Rollout",
                        None, now.isoformat(), "In Progress")
    job["rolloutId"] = rollout_id
    await raw(db).patch_deployment_jobs.update_one({"id": job_id, "tenantId": tenant_id}, {"$setOnInsert": job},
                                                   upsert=True)


async def _busy(db, tenant_id: str, rollout_id: str, agent_id: str) -> bool:
    """Another patch job (not of this rollout) is still waiting for this computer's result."""
    key = agent_id.replace(".", "_").replace("$", "_")
    found = raw(db).patch_deployment_jobs.find(
        {"tenantId": tenant_id, "status": "In Progress", "dispatchedAgents": agent_id,
         "rolloutId": {"$ne": rollout_id}}, {"_id": 0, "agentResults": 1})
    async for job in found:
        if key not in (job.get("agentResults") or {}):
            return True
    return False


async def host_problem(db, tenant_id: str, rollout_id: str, row: Dict[str, Any], agent_id: str,
                       now: datetime) -> Optional[str]:
    """A code when the computer cannot take the row now, else None. Anything unreadable counts as a problem."""
    try:
        rollout = await store.rollouts(db).find_one({"id": rollout_id, "tenantId": tenant_id}, {"_id": 0, "status": 1})
        if rollout is None or rollout.get("status") != "running":
            return "rollout_not_running"
        claim = await store.hosts(db).find_one(
            {"tenantId": tenant_id, "rolloutId": rollout_id, "agentId": agent_id, "active": True}, {"_id": 1})
        if claim is None:
            return "claim_released"
        agent = await raw(db).agents.find_one({"id": agent_id, "tenantId": tenant_id}, _AGENT_FIELDS)
        if agent is None:
            return "no_target"
        permitted = await agent_capabilities.allowed_for(raw(db), tenant_id)
        needed = {CAPABILITY, agent_capabilities.instruction_capability({"type": row.get("command")})} - {None}
        if not needed <= set(permitted):
            return "capability_off"
        if not agent_support.online(agent, now):
            return "agent_offline"
        token = required_token(row)
        if token is not None and token not in agent_support.tokens_of(agent):
            return "agent_unsupported"
        if await _busy(db, tenant_id, rollout_id, agent_id):
            return "busy"
    except Exception as exc:
        logger.error("autonomous_ops: rollout dispatch check for %s failed, holding the row: %s", row.get("id"), exc)
        return "unreadable"
    return None


async def _end(db, row: Dict[str, Any], to_state: str, code: str) -> None:
    await ledger.transition(db, row["tenantId"], row["id"], ("approved", "dispatching"), to_state, reasonCode=code,
                            reasonText=messages.REASON_TEXT.get(code, "Nothing was dispatched."))


async def send(db, row: Dict[str, Any], now: Optional[datetime] = None,
               tenant_windows: Optional[windows_mod.TenantWindows] = None) -> Dict[str, Any]:
    """Send one approved row if the window is open and its computer can take it. Returns
    ``{"status": "queued", "task_id"}``, ``{"status": "deferred", "reason", "windowOpensAt"}`` (the row stays
    approved) or ``{"status": "refused", "reason"}`` (the row was ended). Never raises for a refusal."""
    now = _now(now)
    tenant_id = row["tenantId"]
    inputs = (row.get("reason") or {}).get("inputs") or {}
    rollout_id = inputs.get("rolloutId")
    agent_id = (row.get("targets") or [None])[0]
    tenant_windows = tenant_windows or await windows_mod.load(db, tenant_id)
    occurrence = tenant_windows.open_at(now)
    if occurrence is None:
        upcoming = windows_mod.next_open(tenant_windows.windows, tenant_windows.zone, now) if tenant_windows.readable else None
        return {"status": "deferred", "reason": "window_closed", "windowOpensAt": upcoming[0] if upcoming else None}
    problem = await host_problem(db, tenant_id, rollout_id, row, agent_id, now)
    if problem:
        return {"status": "deferred", "reason": problem, "windowOpensAt": None}
    claimed = await ledger.transition(db, tenant_id, row["id"], ("approved",), "dispatching")
    if claimed is None:
        return {"status": "deferred", "reason": "already_sent", "windowOpensAt": None}     # a click and a tick met
    params = row.get("params") or {}
    if row.get("command") == COMMAND_INSTALL and params.get("job_id"):
        await ensure_job(db, tenant_id, rollout_id, agent_id, params.get("patch_ids") or [], params["job_id"], now)
    result = await gate.execute(db, tenant_id, row["id"], command=row.get("command"), agent_id=agent_id,
                                params=params, kind="action", expires_at=occurrence[1])
    if result.get("status") == "queued":
        if row.get("command") == COMMAND_INSTALL:
            await store.set_host(db, tenant_id, rollout_id, agent_id, {"state": "installing", "waitReason": None})
        elif row.get("command") == reboots.COMMAND:        # D-08: what the computer looked like before it restarted
            await reboots.record_baseline(db, tenant_id, {"rolloutId": rollout_id, "agentId": agent_id}, None, now)
        return result
    if result.get("reason") == "stopped":
        await _end(db, row, "cancelled_by_stop", "platform_stop")
    else:
        await _end(db, row, "failed", "rollout_not_delivered")
    return {"status": "refused", "reason": result.get("reason") or "dispatch_failed"}


async def dispatcher(db, row: Dict[str, Any], approver: Dict[str, Any]) -> Dict[str, Any]:
    """The approvals dispatcher: the row is already ``approved``."""
    return await send(db, row)


async def dispatch_approved(db, tenant_id: str, rollout: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, int]:
    """Send every approved row of the rollout, oldest first, when the window is open. Returns counts of
    ``sent``, ``deferred`` and ``refused``. A row that fails is logged and the others still go."""
    now = _now(now)
    counts = {"sent": 0, "deferred": 0, "refused": 0}
    tenant_windows = await windows_mod.load(db, tenant_id)
    if tenant_windows.open_at(now) is None:
        return counts
    found = raw(db).autonomy_actions.find(
        {"tenantId": tenant_id, "dispatcher": DISPATCHER_NAME, "reason.inputs.rolloutId": rollout["id"],
         "state": "approved"}, {"_id": 0}).sort([("createdAt", 1), ("id", 1)])
    for row in [r async for r in found]:
        try:
            result = await send(db, row, now, tenant_windows)
        except Exception as exc:
            logger.error("autonomous_ops: approved rollout row %s not sent: %s", row.get("id"), exc)
            counts["refused"] += 1
            continue
        key = {"queued": "sent", "deferred": "deferred"}.get(result.get("status"), "refused")
        counts[key] += 1
    return counts


approvals.register_dispatcher(DISPATCHER_NAME, dispatcher)
