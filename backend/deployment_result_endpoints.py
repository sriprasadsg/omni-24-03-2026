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


# ── Agent instruction poll ───────────────────────────────────────────────────

@router.get("/api/agents/{agent_id}/instructions")
async def get_agent_instructions(agent_id: str, caller: dict = Depends(_get_caller)):
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
            "payload":     instr.get("payload", {}),
            "patches":     instr.get("metadata", {}).get("patches", []),
            "job_id":      instr.get("job_id"),
        }
        for instr in instructions
    ]


# ── Deployment result callback ────────────────────────────────────────────────

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
    db = get_database()

    status_map = {
        "completed": "Completed",
        "partial":   "Partially Completed",
        "failed":    "Failed",
    }
    job_status = status_map.get(data.get("status", "failed"), "Failed")
    results    = data.get("results", [])
    successful = data.get("successful", 0)
    failed_cnt = data.get("failed", 0)
    total      = data.get("total", 0)
    reboot_required = any(r.get("reboot_required") for r in results)

    # Build per-patch log entries
    status_log: List[Dict] = [
        {
            "timestamp": r.get("timestamp", datetime.now(timezone.utc).isoformat()),
            "message":   f"{r.get('patch_id')}: {r.get('message', r.get('status'))}",
            "level":     "error" if r.get("status") == "failed" else "info",
        }
        for r in results
    ]
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
