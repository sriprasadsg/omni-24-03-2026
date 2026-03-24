from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import uuid
from database import get_database
from tasks import run_agent_task_async

router = APIRouter(prefix="/api/simulation", tags=["Simulation"])

@router.post("/process-injection")
async def trigger_process_injection(data: Dict[str, Any]):
    """
    Trigger a process injection simulation on an agent.
    Payload: {"agentId": "agent-1", "technique": "memory_write", "target": "notepad.exe", "tenantId": "default"}
    """
    agent_id = data.get("agentId")
    technique = data.get("technique", "memory_write")
    target = data.get("target", "notepad.exe")
    tenant_id = data.get("tenantId", "default")
    
    if not agent_id:
        raise HTTPException(status_code=400, detail="agentId is required")
    
    db = get_database()
    
    # 1. Create a Security Case for tracking
    case_id = f"SIM-{uuid.uuid4().hex[:8]}"
    case = {
        "id": case_id,
        "tenantId": tenant_id,
        "title": f"Process Injection Simulation: {technique}",
        "description": f"Benign simulation of process injection using {technique} on {target}.",
        "severity": "Low",
        "status": "Open",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "relatedEvents": [],
        "artifacts": [
            {"type": "simulation_info", "technique": technique, "target": target}
        ]
    }
    
    await db.security_cases.insert_one(case)
    
    # 2. Dispatch task to agent
    instruction = f"Simulate Process Injection: technique={technique}, target={target}"
    # Dispatch via Celery
    task = run_agent_task_async.delay(instruction, agent_id)
    
    # 3. Log simulation history
    simulation_record = {
        "id": uuid.uuid4().hex,
        "tenantId": tenant_id,
        "agentId": agent_id,
        "type": "process_injection",
        "technique": technique,
        "target": target,
        "caseId": case_id,
        "taskId": task.id,
        "status": "Dispatched",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    await db.simulations.insert_one(simulation_record)
    
    return {
        "success": True,
        "message": "Simulation dispatched to agent",
        "caseId": case_id,
        "taskId": task.id
    }

@router.get("/history")
async def get_simulation_history(tenant_id: str = "default"):
    """Get history of simulations"""
    db = get_database()
    history = await db.simulations.find({"tenantId": tenant_id}, {"_id": 0}).sort("timestamp", -1).to_list(length=100)
    return history
