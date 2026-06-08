"""
Autonomous Response API Endpoints
CRUD for response policies + manual/automated response action dispatch.
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.background import BackgroundTasks
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData
from response_orchestrator import ResponseOrchestrator, seed_builtin_policies

router = APIRouter(prefix="/api/response", tags=["Autonomous Response"])
orchestrator = ResponseOrchestrator()

_SUPER_ADMIN_ROLES = {"Super Admin", "superadmin", "super_admin", "platform-admin"}


def _tenant_filter(current_user: TokenData) -> dict:
    role = getattr(current_user, "role", "") or ""
    if role in _SUPER_ADMIN_ROLES:
        return {}
    tid = getattr(current_user, "tenant_id", None)
    return {"tenantId": tid} if tid else {"tenantId": {"$exists": False}}


# ------------------------------------------------------------------
# Pydantic Models
# ------------------------------------------------------------------

class PolicyCondition(BaseModel):
    field: str = Field(..., max_length=100)
    operator: str = Field(..., max_length=20)   # eq | ne | in | contains
    value: Any


class PolicyAction(BaseModel):
    action: str = Field(..., max_length=100)    # kill_process | quarantine_file | isolate_host | restore_host
    params: Dict[str, Any] = {}


class ResponsePolicy(BaseModel):
    policy_id: str = Field(..., max_length=100)
    name: str = Field(..., max_length=255)
    description: str = Field("", max_length=2000)
    enabled: bool = True
    conditions: List[PolicyCondition]
    actions: List[PolicyAction]
    notify_on_trigger: bool = True


class ManualAction(BaseModel):
    agent_id: str = Field(..., max_length=100)
    action: str = Field(..., max_length=100)
    params: Dict[str, Any] = {}
    reason: str = Field("manual_operator_action", max_length=500)


class TaskResult(BaseModel):
    success: bool
    message: str = Field(..., max_length=2000)
    metadata: Dict[str, Any] = {}


class TaskFeedback(BaseModel):
    success: bool
    false_positive: bool = False
    message: str = Field("", max_length=2000)
    reported_by: str = Field("agent", max_length=100)


# ------------------------------------------------------------------
# Policies CRUD
# ------------------------------------------------------------------

@router.get("/policies")
async def list_policies(current_user: TokenData = Depends(get_current_user)):
    """List response policies scoped to the caller's tenant."""
    db = get_database()
    policies = await db.response_policies.find(
        _tenant_filter(current_user), {"_id": 0}
    ).to_list(length=100)
    return policies


@router.post("/policies")
async def create_policy(
    policy: ResponsePolicy,
    current_user: TokenData = Depends(get_current_user)
):
    """Create a new response policy."""
    db = get_database()
    _role = getattr(current_user, "role", "") or ""
    tenant_id = getattr(current_user, "tenant_id", None) or None
    if not tenant_id and _role not in _SUPER_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Tenant context required")
    existing = await db.response_policies.find_one(
        {"policy_id": policy.policy_id, **_tenant_filter(current_user)}
    )
    if existing:
        raise HTTPException(status_code=409, detail="Policy ID already exists")
    doc = {
        **policy.dict(),
        "tenantId": tenant_id,
        "created_by": getattr(current_user, "username", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
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
    policy = await db.response_policies.find_one(
        {"policy_id": policy_id, **_tenant_filter(current_user)}
    )
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    new_state = not policy.get("enabled", True)
    await db.response_policies.update_one(
        {"policy_id": policy_id, **_tenant_filter(current_user)},
        {"$set": {"enabled": new_state, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"policy_id": policy_id, "enabled": new_state}


@router.delete("/policies/{policy_id}")
async def delete_policy(
    policy_id: str,
    current_user: TokenData = Depends(get_current_user)
):
    """Delete a custom response policy (cannot delete built-ins)."""
    db = get_database()
    policy = await db.response_policies.find_one(
        {"policy_id": policy_id, **_tenant_filter(current_user)}
    )
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    if policy.get("builtin"):
        raise HTTPException(status_code=403, detail="Cannot delete built-in policies")
    await db.response_policies.delete_one({"policy_id": policy_id, **_tenant_filter(current_user)})
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
    """Manually dispatch a response action to an agent."""
    db = get_database()
    _exec_role = getattr(current_user, "role", "") or ""
    _exec_tid = getattr(current_user, "tenant_id", None) or None
    if not _exec_tid and _exec_role not in _SUPER_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Tenant context required")
    task = {
        "task_id": f"MAN-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        "agent_id": action.agent_id,
        "tenantId": _exec_tid,
        "action": action.action,
        "params": action.params,
        "reason": action.reason,
        "triggered_by_policy": None,
        "triggered_by_operator": getattr(current_user, "username", ""),
        "status": "queued",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "executed_at": None,
        "result": None,
    }
    await db.response_tasks.insert_one(task)
    task.pop("_id", None)
    return {"status": "queued", "task": task}


@router.get("/tasks/{agent_id}")
async def get_pending_tasks(
    agent_id: str,
    current_user: TokenData = Depends(get_current_user)
):
    """Agent polling endpoint — returns queued response tasks for this agent."""
    tenant_id = getattr(current_user, "tenant_id", None)
    db = get_database()
    agent = await db.agents.find_one({"id": agent_id, "tenantId": tenant_id}, {"_id": 1})
    if not agent:
        raise HTTPException(status_code=403, detail="Agent not found or not in your tenant")
    return await orchestrator.get_pending_tasks(agent_id, tenant_id=tenant_id)


@router.post("/tasks/{task_id}/result")
async def submit_task_result(
    task_id: str,
    result: TaskResult,
    current_user: TokenData = Depends(get_current_user)
):
    """Agent submits the result of a completed response task."""
    tenant_id = getattr(current_user, "tenant_id", None)
    db = get_database()
    task = await db.response_tasks.find_one({"task_id": task_id, "tenantId": tenant_id}, {"_id": 1})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    success = await orchestrator.mark_executed(task_id, result.dict())
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "recorded", "task_id": task_id}


@router.post("/tasks/{task_id}/feedback")
async def submit_task_feedback(
    task_id: str,
    feedback: TaskFeedback,
    current_user: TokenData = Depends(get_current_user)
):
    """Submit execution feedback for a completed task."""
    caller_tenant = getattr(current_user, "tenant_id", None)
    caller_role = getattr(current_user, "role", "")
    success = await orchestrator.record_feedback(
        task_id=task_id,
        success=feedback.success,
        false_positive=feedback.false_positive,
        message=feedback.message,
        reported_by=feedback.reported_by,
        tenant_id=caller_tenant,
        is_super_admin=caller_role in {"super_admin", "Super Admin", "superadmin", "platform-admin"},
    )
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "feedback_recorded", "task_id": task_id}


# ------------------------------------------------------------------
# Response History
# ------------------------------------------------------------------

@router.get("/history")
async def get_response_history(
    agent_id: Optional[str] = None,
    limit: int = 100,
    current_user: TokenData = Depends(get_current_user)
):
    """Get response action history scoped to the caller's tenant."""
    db = get_database()
    query: Dict[str, Any] = {"status": "executed", **_tenant_filter(current_user)}
    if agent_id:
        query["agent_id"] = agent_id
    tasks = await db.response_tasks.find(
        query, {"_id": 0}
    ).sort("executed_at", -1).limit(min(limit, 500)).to_list(length=min(limit, 500))
    return tasks


@router.get("/quarantine")
async def list_quarantine(
    current_user: TokenData = Depends(get_current_user)
):
    """List quarantined files scoped to the caller's tenant."""
    db = get_database()
    docs = await db.response_tasks.find(
        {"action": "quarantine_file", "status": "executed", **_tenant_filter(current_user)},
        {"_id": 0}
    ).sort("executed_at", -1).to_list(length=200)
    return docs


# ------------------------------------------------------------------
# Seed built-in policies on startup
# ------------------------------------------------------------------

async def initialize_response_module():
    """Call this from app.py startup to seed built-in policies."""
    await seed_builtin_policies()
