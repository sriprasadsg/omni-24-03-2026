"""
Deployment Result & Agent Instruction Endpoints

Agents poll /api/agents/:id/instructions to get pending work.
After executing a patch or software deployment, agents POST the result
to /api/deployments/:job_id/result — which updates the job progress
tracked by the frontend dashboard.
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Any, Dict, List
from datetime import datetime, timezone

from database import get_database
from authentication_service import verify_token_async
from tunnel_endpoints import deliverable_payload
import agent_capabilities

router = APIRouter(tags=["Deployment Results"])


# ── Auth helper: accept both user tokens and agent tokens ────────────────────

async def _get_caller(request: Request) -> Dict[str, str]:
    """
    Accept any valid JWT (user or agent).
    Agents carry role='agent'; users carry their RBAC role.
    Returns a minimal dict with agent_id or username.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = auth.split(" ", 1)[1]
    payload = await verify_token_async(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload


async def _require_job_reporter(caller, job_id: str) -> None:
    """People need manage:patches; an agent may only report on a deployment
    job that targets its own asset."""
    if getattr(caller, "role", "") != "agent":
        from rbac_utils import verify_permission
        if not await verify_permission(caller, "manage:patches"):
            raise HTTPException(status_code=403, detail="Missing required permission: manage:patches")
        return
    db = get_database()
    job = (await db.patch_deployment_jobs.find_one({"id": job_id}, {"_id": 0, "targetAssets": 1, "dispatchedAgents": 1})
           or await db.software_deployment_jobs.find_one({"id": job_id}, {"_id": 0, "targetAssetIds": 1}))
    if not job:
        raise HTTPException(status_code=404, detail="Deployment job not found")
    targets = list({*(job.get("targetAssets") or []), *(job.get("targetAssetIds") or [])})
    if caller.username in (job.get("dispatchedAgents") or []) or caller.username in targets:
        return
    agent = await db.agents.find_one({"id": caller.username}, {"_id": 0, "hostname": 1})
    if agent and agent.get("hostname") and f"asset-{agent['hostname']}" in targets:
        return
    if targets and await db.assets.find_one({"id": {"$in": targets}, "agentId": caller.username}, {"_id": 1}):
        return
    raise HTTPException(status_code=403, detail="This deployment job does not target this agent")


# ── Agent instruction poll ───────────────────────────────────────────────────

@router.get("/api/agents/{agent_id}/instructions")
async def get_agent_instructions(agent_id: str, request: Request, caller: dict = Depends(_get_caller)):
    """
    Agent polls this endpoint to fetch pending instructions.
    Delivered instructions are marked so they are not re-delivered.
    """
    db = get_database()

    # Resolve the canonical agent_id (agent may pass its hostname). Scoped
    # by the caller's own tenant (from its verified token, not
    # client-suppliable) — without this, a hostname collision across
    # tenants lets one tenant's agent resolve to a different tenant's
    # agent document (cross-tenant data leak class, and the reason a
    # re-registered host with a leftover doc under a different tenant
    # silently never received instructions).
    caller_tenant_id = caller.get("tenant_id")
    agent = await db.agents.find_one(
        {"$or": [{"id": agent_id}, {"hostname": agent_id}], "tenantId": caller_tenant_id},
        {"id": 1},
    )
    actual_id = agent["id"] if agent else agent_id

    instructions = await db.agent_instructions.find(
        {"agent_id": actual_id, "status": "pending"}
    ).to_list(length=100)
    # An instruction needing a capability the tenant's agents lack is refused, never delivered.
    instructions = await agent_capabilities.hold_back(db, caller_tenant_id, instructions)

    if instructions:
        ids = [i["_id"] for i in instructions]
        await db.agent_instructions.update_many(
            {"_id": {"$in": ids}},
            {"$set": {
                "status": "delivered",
                "delivered_at": datetime.now(timezone.utc).isoformat(),
            }},
        )

    return [
        {
            "id":          str(instr.get("_id", "")),
            "type":        instr.get("type"),
            "instruction": instr.get("instruction"),
            "payload":     deliverable_payload(instr, request),
            "patches":     instr.get("metadata", {}).get("patches", []),
            "job_id":      instr.get("job_id"),
        }
        for instr in instructions
    ]


# ── Deployment result callback ────────────────────────────────────────────────

_STATUS_MAP = {
    "completed": "Completed",
    "partial":   "Partially Completed",
    "failed":    "Failed",
}


# Per-patch outcomes after which the update is no longer pending on the host:
# installed now, or skipped as already installed / no longer offered.
_CLEARED_STATUSES = {"success", "skipped"}


async def clear_installed_from_pending(db, agent_id: str, results: List[Dict]) -> None:
    """Drop the patches an install job just cleared from the agent's stored pending
    lists, so the OS Patches tab stops listing them as soon as the job reports.
    Agents rescan pending updates on their own schedule (the Python agent hourly),
    and their next scan replaces these lists anyway."""
    from patch_core_endpoints import pending_entry_id
    done = {pending_entry_id(r.get("patch_id")) for r in results
            if r.get("status") in _CLEARED_STATUSES} - {None}
    if not done:
        return
    agent = await db.agents.find_one(
        {"id": agent_id}, {"_id": 0, "meta.system_patching": 1, "meta.os_patches": 1, "pending_os_updates": 1})
    if not agent:
        return
    meta = agent.get("meta") or {}
    update: Dict[str, Any] = {}
    for path, items_key, count_key in (("meta.system_patching", "pending_updates", "pending_update_count"),
                                       ("meta.os_patches", "items", "pending_count")):
        section = meta.get(path.split(".", 1)[1]) or {}
        items = section.get(items_key)
        if not isinstance(items, list):
            continue
        left = [i for i in items if pending_entry_id(i) not in done]
        if len(left) == len(items):
            continue
        update[f"{path}.{items_key}"] = left
        # The count can exceed the list, which agents cap at 50 entries.
        count = section.get(count_key)
        count = count if isinstance(count, int) else len(items)
        update[f"{path}.{count_key}"] = max(len(left), count - (len(items) - len(left)))
    legacy = agent.get("pending_os_updates")
    if isinstance(legacy, list):
        left = [i for i in legacy if pending_entry_id(i) not in done]
        if len(left) != len(legacy):
            update["pending_os_updates"] = left
    if update:
        await db.agents.update_one({"id": agent_id}, {"$set": update})


def _result_log(results: List[Dict], prefix: str) -> List[Dict]:
    return [
        {
            "timestamp": str(r.get("timestamp") or datetime.now(timezone.utc).isoformat()),
            "message":   f"{prefix}{r.get('patch_id')}: {str(r.get('message', r.get('status')))[:500]}",
            "level":     "error" if r.get("status") == "failed" else "info",
        }
        for r in results
    ]


async def record_agent_patch_result(db, job_id: str, agent_id: str, data: Dict[str, Any]) -> str:
    """Record one agent's outcome on a multi-agent patch job and recompute the job.

    The job stays "In Progress" until every dispatched agent has reported; then it
    is Completed (all succeeded), Failed (none did) or Partially Completed.
    Returns the job status after this report."""
    now = datetime.now(timezone.utc).isoformat()
    results = [r for r in data.get("results", []) if isinstance(r, dict)][:200]
    agent_status = _STATUS_MAP.get(data.get("status", "failed"), "Failed")
    entry = {
        "status":         agent_status,
        "successful":     int(data.get("successful", 0) or 0),
        "failed":         int(data.get("failed", 0) or 0),
        "total":          int(data.get("total", len(results)) or 0),
        "rebootRequired": any(r.get("reboot_required") for r in results),
        "error":          str(data.get("error") or "")[:500] or None,
        "results":        results,
        "reportedAt":     now,
    }
    key = agent_id.replace(".", "_").replace("$", "_")
    log = _result_log(results, prefix=f"{agent_id}: ")
    log.append({
        "timestamp": now,
        "message":   (f"{agent_id}: {agent_status} — {entry['successful']}/{entry['total']} installed"
                      + (f" — {entry['error']}" if entry["error"] else "")
                      + (" — REBOOT REQUIRED" if entry["rebootRequired"] else "")),
        "level":     "info" if agent_status == "Completed" else "error" if agent_status == "Failed" else "warn",
    })
    await db.patch_deployment_jobs.update_one(
        {"id": job_id},
        {"$set": {f"agentResults.{key}": entry}, "$push": {"statusLog": {"$each": log}}},
    )

    job = await db.patch_deployment_jobs.find_one(
        {"id": job_id}, {"_id": 0, "dispatchedAgents": 1, "agentResults": 1, "type": 1}) or {}
    # A rollback makes packages pending again; the agent's next scan reports those.
    if job.get("type") != "Patch Rollback":
        await clear_installed_from_pending(db, agent_id, results)
    # Jobs created before per-agent tracking have no dispatchedAgents: this report decides them.
    dispatched = [a.replace(".", "_").replace("$", "_") for a in job.get("dispatchedAgents") or []] or [key]
    reported = {k: v for k, v in (job.get("agentResults") or {}).items() if k in dispatched}
    if len(reported) < len(dispatched):
        progress = int(len(reported) / len(dispatched) * 100) if dispatched else 0
        await db.patch_deployment_jobs.update_one({"id": job_id}, {"$set": {"progress": min(progress, 99)}})
        return "In Progress"

    statuses = {v.get("status") for v in reported.values()}
    final = ("Completed" if statuses == {"Completed"}
             else "Failed" if statuses == {"Failed"} else "Partially Completed")
    await db.patch_deployment_jobs.update_one({"id": job_id}, {"$set": {
        "status":         final,
        "progress":       100,
        "completedAt":    now,
        "rebootRequired": any(v.get("rebootRequired") for v in reported.values()),
    }})
    return final


@router.post("/api/deployments/{job_id}/result")
async def receive_deployment_result(
    job_id: str,
    data: Dict[str, Any],
    caller: dict = Depends(_get_caller),
):
    """
    Agent reports the outcome of a patch or software deployment back to the platform.

    Accepted fields in `data`:
      status      : "completed" | "partial" | "failed"
      successful  : int
      failed      : int
      total       : int
      results     : [{patch_id, status, message, reboot_required, timestamp}]
    """
    await _require_job_reporter(caller, job_id)
    db = get_database()

    if getattr(caller, "role", "") == "agent":
        patch_job = await db.patch_deployment_jobs.find_one(
            {"id": job_id}, {"_id": 0, "dispatchedAgents": 1})
        if patch_job and patch_job.get("dispatchedAgents"):
            recorded = await record_agent_patch_result(db, job_id, caller.username, data)
            return {"status": "success", "job_id": job_id, "recorded": recorded}

    job_status = _STATUS_MAP.get(data.get("status", "failed"), "Failed")
    results    = [r for r in data.get("results", []) if isinstance(r, dict)]
    successful = data.get("successful", 0)
    failed_cnt = data.get("failed", 0)
    total      = data.get("total", 0)
    reboot_required = any(r.get("reboot_required") for r in results)

    status_log = _result_log(results, prefix="")
    status_log.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message":   (
            f"Deployment complete — {successful}/{total} succeeded, "
            f"{failed_cnt}/{total} failed"
            + (" — REBOOT REQUIRED" if reboot_required else "")
        ),
        "level": "warn" if failed_cnt else "info",
    })

    update = {
        "status":          job_status,
        "progress":        100,
        "completedAt":     datetime.now(timezone.utc).isoformat(),
        "actualResults":   data,
        "rebootRequired":  reboot_required,
    }

    # Try patch deployment jobs first, then software deployment jobs
    res = await db.patch_deployment_jobs.update_one(
        {"id": job_id},
        {"$set": update, "$push": {"statusLog": {"$each": status_log}}},
    )
    if res.matched_count == 0:
        await db.software_deployment_jobs.update_one(
            {"id": job_id},
            {"$set": update, "$push": {"statusLog": {"$each": status_log}}},
        )

    return {"status": "success", "job_id": job_id, "recorded": job_status}


# ── Per-asset progress update (incremental) ───────────────────────────────────

@router.patch("/api/patches/deployment-jobs/{job_id}/progress")
async def update_job_progress(
    job_id: str,
    data: Dict[str, Any],
    caller: dict = Depends(_get_caller),
):
    """
    Report incremental progress for a single asset within a multi-asset job.
    Agents call this after each patch to give a live progress percentage.

    Body: { agent_id, completed, total, latest_patch_id, latest_status }
    """
    await _require_job_reporter(caller, job_id)
    db = get_database()

    completed = int(data.get("completed", 0))
    total     = int(data.get("total", 1))
    progress  = min(99, int(completed / total * 100)) if total else 0

    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message":   (
            f"Agent {data.get('agent_id','?')}: "
            f"{data.get('latest_patch_id','?')} → {data.get('latest_status','?')} "
            f"({completed}/{total})"
        ),
        "level": "error" if data.get("latest_status") == "failed" else "info",
    }

    await db.patch_deployment_jobs.update_one(
        {"id": job_id},
        {"$set": {"progress": progress}, "$push": {"statusLog": log_entry}},
    )
    return {"job_id": job_id, "progress": progress}
