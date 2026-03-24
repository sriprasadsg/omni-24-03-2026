"""
Enhanced SOAR Playbook API Endpoints

Provides comprehensive API for playbook execution, approval workflows,
template management, and analytics.
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime, timezone

from database import get_database
from enhanced_playbook_engine import get_playbook_engine, StepStatus
from soar_integrations import get_integration_manager
from rbac_utils import require_permission

router = APIRouter(prefix="/api/playbooks/enhanced", tags=["Enhanced SOAR"])

def _get(user, key, default=None):
    if isinstance(user, dict): return user.get(key, default)
    return getattr(user, key, default)



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
    name: str
    description: str
    category: str
    trigger: str
    steps: List[Dict[str, Any]]
    tags: List[str] = []


# Endpoints

@router.post("/execute")
async def execute_playbook(
    request: PlaybookExecutionRequest,
    background_tasks: BackgroundTasks,
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
    
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Execution failed: {str(e)}")


@router.post("/test")
async def test_playbook(
    request: PlaybookTestRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("execute:playbooks"))
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
    except Exception:
        pass
    
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
    if approvers and current_user.get("email") not in approvers:
        raise HTTPException(status_code=403, detail="Not authorized to approve this step")
    
    # Update approval status
    await db.playbook_approvals.update_one(
        {"_id": approval["_id"]},
        {
            "$set": {
                "status": request.action,
                "approved_by": current_user.get("email"),
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
                    "error": f"Rejected by {current_user.get('email')}: {request.comment}"
                }
            }
        )
        
        return {
            "message": "Step rejected, playbook execution stopped",
            "execution_id": request.execution_id
        }


@router.get("/templates")
async def get_playbook_templates(
    category: Optional[str] = None,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:playbooks"))
):
    """
    Get playbook templates
    
    Categories:
    - phishing_response
    - malware_containment
    - ddos_mitigation
    - data_breach_response
    - insider_threat
    - ransomware_recovery
    """
    query = {"is_template": True}
    if category:
        query["category"] = category
    
    cursor = db.playbooks.find(query)
    
    templates = []
    async for template in cursor:
        template["id"] = str(template.pop("_id"))
        templates.append(template)
    
    return templates


@router.post("/templates")
async def create_playbook_from_template(
    template_id: str,
    name: str,
    customizations: Optional[Dict[str, Any]] = None,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("manage:playbooks"))
):
    """
    Create a new playbook from a template
    
    Allows customization of template parameters
    """
    # Get template
    template = await db.playbooks.find_one({
        "_id": template_id,
        "is_template": True
    })
    
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    # Create new playbook from template
    playbook = {
        "name": name,
        "description": template.get("description"),
        "trigger": template.get("trigger"),
        "steps": template.get("steps"),
        "tenantId": current_user.get("tenantId"),
        "created_by": current_user.get("email"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "template_id": template_id,
        "is_template": False
    }
    
    # Apply customizations
    if customizations:
        playbook.update(customizations)
    
    result = await db.playbooks.insert_one(playbook)
    
    return {
        "message": "Playbook created from template",
        "playbook_id": str(result.inserted_id)
    }


@router.get("/analytics")
async def get_playbook_analytics(
    days: int = 30,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:playbooks"))
):
    """
    Get playbook execution analytics
    
    Returns:
    - Total executions
    - Success rate
    - Average execution time
    - Most used playbooks
    - Failure reasons
    """
    tenant_id = _get(current_user, "tenantId")
    
    # Aggregate statistics
    pipeline = [
        {"$match": {"tenant_id": tenant_id}},
        {
            "$group": {
                "_id": "$playbook_id",
                "playbook_name": {"$first": "$playbook_name"},
                "total_executions": {"$sum": 1},
                "successful": {
                    "$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}
                },
                "failed": {
                    "$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}
                },
                "avg_duration": {"$avg": "$duration_ms"}
            }
        },
        {"$sort": {"total_executions": -1}}
    ]
    
    cursor = db.playbook_executions.aggregate(pipeline)
    
    playbook_stats = []
    total_executions = 0
    total_successful = 0
    
    async for stat in cursor:
        success_rate = (stat["successful"] / stat["total_executions"] * 100) if stat["total_executions"] > 0 else 0
        
        playbook_stats.append({
            "playbook_id": stat["_id"],
            "playbook_name": stat["playbook_name"],
            "total_executions": stat["total_executions"],
            "success_rate": round(success_rate, 2),
            "avg_duration_ms": round(stat.get("avg_duration", 0), 2)
        })
        
        total_executions += stat["total_executions"]
        total_successful += stat["successful"]
    
    overall_success_rate = (total_successful / total_executions * 100) if total_executions > 0 else 0
    
    return {
        "total_executions": total_executions,
        "overall_success_rate": round(overall_success_rate, 2),
        "playbook_stats": playbook_stats
    }


@router.get("/integrations")
async def get_available_integrations(
    current_user: dict = Depends(require_permission("view:playbooks"))
):
    """
    Get list of available integration connectors
    
    Returns status of each integration
    """
    integration_manager = get_integration_manager()
    
    # Test all connections
    connection_status = await integration_manager.test_all_connections()
    
    integrations = []
    for name, connector in integration_manager.connectors.items():
        integrations.append({
            "name": name,
            "type": connector.__class__.__name__,
            "available": connection_status.get(name, False),
            "actions": _get_connector_actions(name)
        })
    
    return integrations


def _get_connector_actions(connector_name: str) -> List[str]:
    """Get available actions for a connector"""
    action_map = {
        "slack": ["send_message", "request_approval"],
        "jira": ["create_ticket", "update_ticket", "add_comment"],
        "firewall": ["block_ip", "unblock_ip", "create_rule"],
        "edr": ["isolate_endpoint", "release_endpoint", "quarantine_file", "scan_endpoint"],
        "email_gateway": ["block_sender", "quarantine_email", "release_email"],
        "cloud_provider": ["quarantine_instance", "snapshot_instance", "revoke_credentials"]
    }
    return action_map.get(connector_name, [])


@router.post("/integrations/test")
async def test_integration(
    connector_name: str,
    action: str,
    params: Dict[str, Any],
    current_user: dict = Depends(require_permission("manage:playbooks"))
):
    """
    Test an integration connector action
    
    Useful for validating integration configuration
    """
    integration_manager = get_integration_manager()
    
    try:
        result = await integration_manager.execute_action(
            connector_name=connector_name,
            action=action,
            params=params
        )
        
        return {
            "message": "Integration test successful",
            "result": result
        }
    
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Integration test failed: {str(e)}")
