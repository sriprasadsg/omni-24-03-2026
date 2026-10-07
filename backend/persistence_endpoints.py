from fastapi import APIRouter, HTTPException, Depends, Body
from typing import Dict, Any
from datetime import datetime, timezone
import uuid
from database import get_database
from authentication_service import get_current_user
from rbac_utils import require_permission
from auth_types import TokenData

router = APIRouter(prefix="/api/persistence", tags=["Persistence"])


async def _queue_agent_instruction(db, agent_ref: str, instruction: str, payload: Dict[str, Any], requested_by: str):
    """Queue an instruction for an agent in the caller's tenant (agents poll agent_instructions)."""
    agent = await db.agents.find_one({"$or": [{"id": agent_ref}, {"hostname": agent_ref}]}, {"id": 1})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    instruction_id = uuid.uuid4().hex
    await db.agent_instructions.insert_one({
        "id": instruction_id,
        "agent_id": agent["id"],
        "instruction": instruction,
        "payload": payload,
        "status": "pending",
        "triggered_by": requested_by,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return agent["id"], instruction_id

@router.get("/")
async def list_persistence_scans(
    limit: int = 50,
    current_user: TokenData = Depends(get_current_user),
):
    """List recent persistence scan results for the tenant"""
    tenant_id = getattr(current_user, "tenant_id", None) or None
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    db = get_database()
    try:
        results = await db.persistence_results.find(
            {"tenantId": tenant_id}, {"_id": 0}
        ).sort("timestamp", -1).limit(limit).to_list(length=limit)
    except Exception:
        results = []
    return results


@router.post("/scan")
async def trigger_persistence_scan(
    data: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(require_permission("investigate:security")),
):
    """
    Trigger a persistence scan on an agent.
    Payload: {"agentId": "agent-1"}
    """
    agent_id = data.get("agentId")
    tenant_id = getattr(current_user, "tenant_id", None) or None
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    
    if not agent_id:
        raise HTTPException(status_code=400, detail="agentId is required")
    
    db = get_database()
    
    # 1. Queue the scan for the agent (runs on the endpoint, not this server)
    agent_id, task_id = await _queue_agent_instruction(
        db, agent_id, "Scan for Persistence", {}, getattr(current_user, "username", "unknown"))
    
    # 2. Log scan request
    scan_record = {
        "id": uuid.uuid4().hex,
        "tenantId": tenant_id,
        "agentId": agent_id,
        "taskId": task_id,
        "status": "Pending",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    await db.persistence_scans.insert_one(scan_record)
    
    return {
        "success": True,
        "message": "Persistence scan dispatched to agent",
        "taskId": task_id
    }

@router.get("/results/{agent_id}")
async def get_persistence_results(
    agent_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Get latest persistence scan results for an agent"""
    tenant_id = getattr(current_user, "tenant_id", None) or None
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    db = get_database()

    results = await db.persistence_results.find(
        {"agentId": agent_id, "tenantId": tenant_id}, {"_id": 0}
    ).sort("timestamp", -1).to_list(length=1)

    if not results:
        return {"findings": [], "count": 0, "message": "No scan results yet. Trigger a scan via POST /api/persistence/scan."}

    return results[0]

@router.post("/report")
async def report_persistence_results(
    data: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(require_permission("investigate:security")),
):
    """Endpoint for agents to report persistence scan results"""
    tenant_id = getattr(current_user, "tenant_id", None) or None
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    db = get_database()

    result_record = {
        "id": uuid.uuid4().hex,
        "tenantId": tenant_id,
        "agentId": data.get("agentId"),
        "findings": data.get("findings", []),
        "count": data.get("count", 0),
        "platform": data.get("platform"),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    await db.persistence_results.insert_one(result_record)

    # Update scan status if taskId provided
    task_id = data.get("taskId")
    if task_id:
        await db.persistence_scans.update_one(
            {"taskId": task_id},
            {"$set": {"status": "Completed", "completedAt": datetime.now(timezone.utc).isoformat()}}
        )

    # Create security events for suspicious findings
    for finding in data.get("findings", []):
        if finding.get("severity") in ["High", "Critical", "Medium"]:
            event = {
                "id": f"EVT-{uuid.uuid4().hex[:8]}",
                "tenantId": tenant_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "severity": finding.get("severity"),
                "type": "Suspicious Persistence",
                "description": f"Suspicious persistence mechanism detected: {finding.get('name')} at {finding.get('location')}",
                "source": {"hostname": data.get("agentId"), "ip": "N/A"},
                "details": finding,
                "status": "New"
            }
            await db.security_events.insert_one(event)
            
    return {"success": True}
