"""
Agent Instruction Endpoints
Manages deployment instructions sent to agents and receives deployment results.
"""

from datetime import datetime, timezone
from typing import Any, Dict
import logging

from fastapi import APIRouter, HTTPException, Depends
from database import get_database
from authentication_service import get_current_user
from rbac_utils import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Agent Instructions"])

_INSTR_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}


@router.get("/api/agents/{agent_id}/instructions")
async def get_agent_instructions(
    agent_id: str,
    current_user=Depends(get_current_user)
):
    """
    Agent polls this endpoint to get pending instructions.
    Returns list of instructions to execute.
    """
    db = get_database()
    user_role = getattr(current_user, "role", "")
    tenant_id = getattr(current_user, "tenant_id", None) or getattr(current_user, "tenantId", None)

    agent_filter: dict = {"$or": [{"id": agent_id}, {"hostname": agent_id}]}
    if user_role not in _INSTR_SUPER_ROLES and tenant_id:
        agent_filter["tenantId"] = tenant_id

    agent = await db.agents.find_one(agent_filter)
    if agent:
        actual_agent_id = agent["id"]
    else:
        raise HTTPException(status_code=404, detail="Agent not found")

    instructions = await db.agent_instructions.find({
        "agent_id": actual_agent_id,
        "status": "pending"
    }).to_list(length=100)

    for instruction in instructions:
        await db.agent_instructions.update_one(
            {"_id": instruction["_id"]},
            {"$set": {"status": "delivered", "delivered_at": datetime.now(timezone.utc).isoformat()}}
        )

    return [
        {
            "id": instr.get("id"),
            "type": instr.get("type"),
            "instruction": instr.get("instruction"),
            "patches": instr.get("patches", []),
            "job_id": instr.get("job_id")
        }
        for instr in instructions
    ]


@router.post("/api/deployments/{job_id}/result")
async def receive_deployment_result(
    job_id: str,
    data: Dict[str, Any],
    current_user=Depends(require_permission("manage:deployments"))
):
    """
    Agent reports deployment result back.
    Updates job status based on actual installation outcomes.
    """
    db = get_database()

    logger.info("Deployment: Received result for job %s: %s", job_id, data.get("status"))

    _INSTR_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}
    caller_role = getattr(current_user, "role", "")
    caller_tenant = getattr(current_user, "tenant_id", None)
    job_filter: dict = {"id": job_id}
    if caller_role not in _INSTR_SUPER_ROLES and caller_tenant:
        job_filter["tenantId"] = caller_tenant

    status = data.get("status", "failed")
    results = data.get("results", [])
    successful = data.get("successful", 0)
    failed = data.get("failed", 0)
    total = data.get("total", 0)

    if status == "completed":
        job_status = "Completed"
    elif status == "partial":
        job_status = "Partially Completed"
    else:
        job_status = "Failed"

    status_log = []
    for result in results:
        status_log.append({
            "timestamp": result.get("timestamp", datetime.now(timezone.utc).isoformat()),
            "message": f"{result.get('patch_id')}: {result.get('message')}",
            "level": "error" if result.get("status") == "failed" else "info"
        })

    status_log.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": f"Deployment complete: {successful}/{total} successful, {failed}/{total} failed"
    })

    update_data = {
        "status": job_status,
        "progress": 100,
        "completedAt": datetime.now(timezone.utc).isoformat(),
        "actualResults": data,
    }

    result = await db.patch_deployment_jobs.update_one(
        job_filter,
        {"$set": update_data, "$push": {"statusLog": {"$each": status_log}}}
    )

    if result.matched_count == 0:
        await db.software_deployment_jobs.update_one(
            job_filter,
            {"$set": update_data, "$push": {"statusLog": {"$each": status_log}}}
        )

    return {"status": "success", "message": "Result recorded"}
