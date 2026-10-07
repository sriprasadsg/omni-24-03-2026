from fastapi import APIRouter, Depends, HTTPException, Body
from typing import Dict, Any
from datetime import datetime, timezone
import uuid
from database import get_database
import re
from authentication_service import get_current_user
from rbac_utils import require_permission
from auth_types import TokenData

router = APIRouter(prefix="/api/simulation", tags=["Simulation"])

# technique/target are spliced into the agent's instruction text
_SAFE_PARAM = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


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

@router.post("/process-injection")
async def trigger_process_injection(
    data: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(require_permission("remediate:agents")),
):
    """
    Trigger a process injection simulation on an agent.
    Payload: {"agentId": "agent-1", "technique": "memory_write", "target": "notepad.exe"}
    """
    agent_id = data.get("agentId")
    technique = data.get("technique", "memory_write")
    target = data.get("target", "notepad.exe")
    tenant_id = getattr(current_user, "tenant_id", None) or None
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    
    if not agent_id:
        raise HTTPException(status_code=400, detail="agentId is required")
    if not (_SAFE_PARAM.match(str(technique)) and _SAFE_PARAM.match(str(target))):
        raise HTTPException(status_code=400, detail="technique and target may only contain letters, digits, '.', '_' and '-'")
    
    db = get_database()

    # 1. Queue for the agent first (404 before anything is recorded); it runs on the endpoint, not this server
    instruction = f"Simulate Process Injection: technique={technique}, target={target}"
    agent_id, task_id = await _queue_agent_instruction(
        db, agent_id, instruction, {"technique": technique, "target": target},
        getattr(current_user, "username", "unknown"))

    # 2. Create a Security Case for tracking
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
    
    # 3. Log simulation history
    simulation_record = {
        "id": uuid.uuid4().hex,
        "tenantId": tenant_id,
        "agentId": agent_id,
        "type": "process_injection",
        "technique": technique,
        "target": target,
        "caseId": case_id,
        "taskId": task_id,
        "status": "Dispatched",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    await db.simulations.insert_one(simulation_record)
    
    return {
        "success": True,
        "message": "Simulation dispatched to agent",
        "caseId": case_id,
        "taskId": task_id
    }

@router.get("/history")
async def get_simulation_history(current_user: TokenData = Depends(get_current_user)):
    """Get history of simulations"""
    tenant_id = getattr(current_user, "tenant_id", None) or None
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    db = get_database()
    history = await db.simulations.find({"tenantId": tenant_id}, {"_id": 0}).sort("timestamp", -1).to_list(length=100)
    return history
