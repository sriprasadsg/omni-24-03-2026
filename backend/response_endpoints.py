"""
Autonomous Response API Endpoints
CRUD for response policies + manual/automated response action dispatch.
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.background import BackgroundTasks
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData
from response_orchestrator import ResponseOrchestrator, BUILTIN_POLICIES, seed_builtin_policies

router = APIRouter(prefix="/api/response", tags=["Autonomous Response"])
orchestrator = ResponseOrchestrator()


# ------------------------------------------------------------------
# Pydantic Models
# ------------------------------------------------------------------

class PolicyCondition(BaseModel):
    field: str
    operator: str   # eq | ne | in | contains
    value: Any


class PolicyAction(BaseModel):
    action: str     # kill_process | quarantine_file | isolate_host | restore_host
    params: Dict[str, Any] = {}


class ResponsePolicy(BaseModel):
    policy_id: str
    name: str
    description: str = ""
    enabled: bool = True
    conditions: List[PolicyCondition]
    actions: List[PolicyAction]
    notify_on_trigger: bool = True


class ManualAction(BaseModel):
    agent_id: str
    action: str               # kill_process | quarantine_file | isolate_host | restore_host | unquarantine_file
    params: Dict[str, Any] = {}
    reason: str = "manual_operator_action"


class TaskResult(BaseModel):
    success: bool
    message: str
    metadata: Dict[str, Any] = {}


# ------------------------------------------------------------------
# Policies CRUD
# ------------------------------------------------------------------

@router.get("/policies")
async def list_policies(current_user: TokenData = Depends(get_current_user)):
    """List all response policies."""
    db = get_database()
    policies = await db.response_policies.find({}, {"_id": 0}).to_list(length=100)
    return policies


@router.post("/policies")
async def create_policy(
    policy: ResponsePolicy,
    current_user: TokenData = Depends(get_current_user)
):
    """Create a new response policy."""
    db = get_database()
    existing = await db.response_policies.find_one({"policy_id": policy.policy_id})
    if existing:
        raise HTTPException(status_code=409, detail="Policy ID already exists")
    doc = {
        **policy.dict(),
        "created_by": current_user.username,
        "created_at": datetime.utcnow().isoformat(),
        "builtin": False,
    }
    await db.response_policies.insert_one(doc)
    doc.pop("_id", None)
    return {"status": "created", "policy": doc}


@router.patch("/policies/{policy_id}/toggle")
async def toggle_policy(
    policy_id: str,
    current_user: TokenData = Depends(get_current_user)
):
    """Enable or disable a response policy."""
    db = get_database()
    policy = await db.response_policies.find_one({"policy_id": policy_id})
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    new_state = not policy.get("enabled", True)
    await db.response_policies.update_one(
        {"policy_id": policy_id},
        {"$set": {"enabled": new_state, "updated_at": datetime.utcnow().isoformat()}}
    )
    return {"policy_id": policy_id, "enabled": new_state}


@router.delete("/policies/{policy_id}")
async def delete_policy(
    policy_id: str,
    current_user: TokenData = Depends(get_current_user)
):
    """Delete a custom response policy (cannot delete built-ins)."""
    db = get_database()
    policy = await db.response_policies.find_one({"policy_id": policy_id})
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    if policy.get("builtin"):
        raise HTTPException(status_code=403, detail="Cannot delete built-in policies")
    await db.response_policies.delete_one({"policy_id": policy_id})
    return {"status": "deleted", "policy_id": policy_id}


# ------------------------------------------------------------------
# Manual Response Actions
# ------------------------------------------------------------------

@router.post("/execute")
async def execute_response_action(
    action: ManualAction,
    background_tasks: BackgroundTasks,
    current_user: TokenData = Depends(get_current_user)
):
    """
    Manually dispatch a response action to an agent.
    The agent polls /response/tasks/{agent_id} and executes queued tasks.
    """
    db = get_database()
    task = {
        "task_id": f"MAN-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}",
        "agent_id": action.agent_id,
        "action": action.action,
        "params": action.params,
        "reason": action.reason,
        "triggered_by_policy": None,
        "triggered_by_operator": current_user.username,
        "status": "queued",
        "created_at": datetime.utcnow().isoformat(),
        "executed_at": None,
        "result": None,
    }
    await db.response_tasks.insert_one(task)
    task.pop("_id", None)
    return {"status": "queued", "task": task}


@router.get("/tasks/{agent_id}")
async def get_pending_tasks(agent_id: str):
    """
    Agent polling endpoint — returns queued response tasks.
    Called by the agent every ~15 seconds.
    No auth required (agent uses registration key instead).
    """
    return await orchestrator.get_pending_tasks(agent_id)


@router.post("/tasks/{task_id}/result")
async def submit_task_result(task_id: str, result: TaskResult):
    """Agent submits the result of a completed response task."""
    success = await orchestrator.mark_executed(task_id, result.dict())
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "recorded", "task_id": task_id}


# ------------------------------------------------------------------
# Response History
# ------------------------------------------------------------------

@router.get("/history")
async def get_response_history(
    agent_id: Optional[str] = None,
    limit: int = 100,
    current_user: TokenData = Depends(get_current_user)
):
    """Get response action history."""
    db = get_database()
    query: Dict[str, Any] = {"status": "executed"}
    if agent_id:
        query["agent_id"] = agent_id
    tasks = await db.response_tasks.find(
        query, {"_id": 0}
    ).sort("executed_at", -1).limit(limit).to_list(length=limit)
    return tasks


@router.get("/quarantine")
async def list_quarantine(
    current_user: TokenData = Depends(get_current_user)
):
    """List all quarantined files across all agents (from DB audit log)."""
    db = get_database()
    docs = await db.response_tasks.find(
        {"action": "quarantine_file", "status": "executed"},
        {"_id": 0}
    ).sort("executed_at", -1).to_list(length=200)
    return docs


# ------------------------------------------------------------------
# Seed built-in policies on startup
# ------------------------------------------------------------------

async def initialize_response_module():
    """Call this from app.py startup to seed built-in policies."""
    await seed_builtin_policies()
