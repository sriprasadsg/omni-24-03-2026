"""
Enhanced SOAR Playbook API Endpoints

Provides comprehensive API for playbook execution, approval workflows,
template management, and analytics.
"""

import logging
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

from database import get_database
from enhanced_playbook_engine import get_playbook_engine
from rbac_utils import require_permission

router = APIRouter(prefix="/api/playbooks/enhanced", tags=["Enhanced SOAR"])

_KEY_ALIASES = {"tenantId": "tenant_id", "email": "username"}

def _get(user, key, default=None):
    if isinstance(user, dict):
        return user.get(key, default)
    attr = _KEY_ALIASES.get(key, key)
    return getattr(user, attr, default)



# Request/Response Models
class PlaybookExecutionRequest(BaseModel):
    playbook_id: str
    trigger_data: Dict[str, Any]


class PlaybookTestRequest(BaseModel):
    playbook_id: str
    trigger_data: Dict[str, Any]
    dry_run: bool = True


class ApprovalActionRequest(BaseModel):
    execution_id: str
    step_index: int
    action: str  # "approve" or "reject"
    comment: Optional[str] = None


class PlaybookTemplate(BaseModel):
    name: str = Field(..., max_length=255)
    description: str = Field(..., max_length=5000)
    category: str = Field(..., max_length=100)
    trigger: str = Field(..., max_length=255)
    steps: List[Dict[str, Any]]
    tags: List[str] = []


# Endpoints

@router.post("/execute")
async def execute_playbook(
    request: PlaybookExecutionRequest,
    _background_tasks: BackgroundTasks,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("execute:playbooks"))
):
    """
    Execute a playbook with advanced flow control
    
    Supports:
    - Conditional branching (if/else/switch)
    - Loops (for/while)
    - Error handling with retry logic
    - Parallel execution
    - Approval gates
    - Variable passing between steps
    """
    engine = get_playbook_engine(db)
    
    try:
        # Execute playbook in background
        result = await engine.execute_playbook(
            playbook_id=request.playbook_id,
            trigger_data=request.trigger_data,
            tenant_id=_get(current_user, "tenantId"),
            executed_by=_get(current_user, "email")
        )
        
        return {
            "message": "Playbook execution initiated",
            "execution_id": result.get("execution_id"),
            "status": result.get("status")
        }
    
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")
    except Exception as e:
        logger.error("Playbook execution failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/test")
async def test_playbook(
    request: PlaybookTestRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
    _current_user: dict = Depends(require_permission("execute:playbooks"))
):
    """
    Test a playbook in dry-run mode
    
    Validates playbook structure and simulates execution without
    actually performing actions.
    """
    # Get playbook
    playbook = await db.playbooks.find_one({"_id": request.playbook_id})
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")
    
    # Validate playbook structure
    validation_errors = []
    
    # Check required fields
    if not playbook.get("name"):
        validation_errors.append("Playbook name is required")
    if not playbook.get("steps"):
        validation_errors.append("Playbook must have at least one step")
    
    # Validate steps
    for idx, step in enumerate(playbook.get("steps", [])):
        if not step.get("type"):
            validation_errors.append(f"Step {idx}: type is required")
        
        if step.get("type") == "action" and not step.get("action"):
            validation_errors.append(f"Step {idx}: action is required for action steps")
        
        if step.get("type") == "condition" and not step.get("condition"):
            validation_errors.append(f"Step {idx}: condition is required for condition steps")
    
    if validation_errors:
        return {
            "valid": False,
            "errors": validation_errors
        }
    
    return {
        "valid": True,
        "message": "Playbook is valid",
        "estimated_duration": len(playbook.get("steps", [])) * 5  # Rough estimate
    }


@router.get("/executions")
async def get_playbook_executions(
    status: Optional[str] = None,
    limit: int = 50,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:playbooks"))
):
    """
    Get playbook execution history
    
    Filter by status: running, completed, failed, waiting_approval
    """
    query = {"tenant_id": _get(current_user, "tenantId")}
    if status:
        query["status"] = status
    
    executions = []
    try:
        cursor = db.playbook_executions.find(query).sort("started_at", -1).limit(limit)
        async for execution in cursor:
            execution["id"] = str(execution.pop("_id"))
            executions.append(execution)
    except Exception as e:
        logger.warning("Failed to fetch playbook executions: %s", e)

    return executions


@router.get("/executions/{execution_id}")
async def get_execution_details(
    execution_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:playbooks"))
):
    """
    Get detailed execution information
    
    Returns full execution trace including:
    - All steps executed
    - Step outputs
    - Variables
    - Errors
    - Timing information
    """
    execution = await db.playbook_executions.find_one({
        "_id": execution_id,
        "tenant_id": _get(current_user, "tenantId")
    })
    
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    
    execution["id"] = str(execution.pop("_id"))
    return execution


@router.post("/approve")
async def approve_playbook_step(
    request: ApprovalActionRequest,
    background_tasks: BackgroundTasks,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("approve:playbooks"))
):
    """
    Approve or reject a playbook step waiting for approval
    
    Actions:
    - approve: Continue playbook execution
    - reject: Stop playbook execution
    """
    # Get approval request
    approval = await db.playbook_approvals.find_one({
        "execution_id": request.execution_id,
        "step_index": request.step_index,
        "status": "pending"
    })
    
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")
    
    # Check if user is authorized approver
    approvers = approval.get("approvers", [])
    actor = getattr(current_user, "username", None) or (current_user.get("email") if isinstance(current_user, dict) else None)
    if approvers and actor not in approvers:
        raise HTTPException(status_code=403, detail="Not authorized to approve this step")

    # Update approval status
    await db.playbook_approvals.update_one(
        {"_id": approval["_id"]},
        {
            "$set": {
                "status": request.action,
                "approved_by": actor,
                "approved_at": datetime.now(timezone.utc).isoformat(),
                "comment": request.comment
            }
        }
    )
    
    # Update execution status
    if request.action == "approve":
        # Resume execution
        engine = get_playbook_engine(db)
        
        # Trigger resumption in background
        background_tasks.add_task(
            engine.resume_playbook_execution,
            execution_id=request.execution_id,
            tenant_id=_get(current_user, "tenantId")
        )
        
        return {
            "message": "Step approved, playbook execution resumed",
            "execution_id": request.execution_id
        }
    else:
        # Reject and stop execution
        await db.playbook_executions.update_one(
            {"_id": request.execution_id},
            {
                "$set": {
                    "status": "rejected",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "error": f"Rejected by {actor}: {request.comment}"
                }
            }
        )
        
        return {
            "message": "Step rejected, playbook execution stopped",
            "execution_id": request.execution_id
        }


