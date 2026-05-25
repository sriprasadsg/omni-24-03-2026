from fastapi import APIRouter, HTTPException, Depends, Body
from typing import List, Dict, Any
from datetime import datetime, timezone
import uuid
from database import get_database
from tasks import run_agent_task_async
from authentication_service import get_current_user
from auth_types import TokenData

router = APIRouter(prefix="/api/persistence", tags=["Persistence"])

@router.get("/")
async def list_persistence_scans(
    limit: int = 50,
    current_user: TokenData = Depends(get_current_user),
):
    """List recent persistence scan results for the tenant"""
    tenant_id = getattr(current_user, "tenant_id", None) or "default"
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
    current_user: TokenData = Depends(get_current_user),
):
    """
    Trigger a persistence scan on an agent.
    Payload: {"agentId": "agent-1"}
    """
    agent_id = data.get("agentId")
    tenant_id = getattr(current_user, "tenant_id", None) or "default"
    
    if not agent_id:
        raise HTTPException(status_code=400, detail="agentId is required")
    
    db = get_database()
    
    # 1. Dispatch task to agent
    instruction = "Scan for Persistence"
    task = run_agent_task_async.delay(instruction, agent_id)
    
    # 2. Log scan request
    scan_record = {
        "id": uuid.uuid4().hex,
        "tenantId": tenant_id,
        "agentId": agent_id,
        "taskId": task.id,
        "status": "Pending",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    await db.persistence_scans.insert_one(scan_record)
    
    return {
        "success": True,
        "message": "Persistence scan dispatched to agent",
        "taskId": task.id
    }

@router.get("/results/{agent_id}")
async def get_persistence_results(
    agent_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Get latest persistence scan results for an agent"""
    tenant_id = getattr(current_user, "tenant_id", None) or "default"
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
    current_user: TokenData = Depends(get_current_user),
):
    """Endpoint for agents to report persistence scan results"""
    tenant_id = getattr(current_user, "tenant_id", None) or "default"
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
