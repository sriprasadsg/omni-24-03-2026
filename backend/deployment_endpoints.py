from fastapi import APIRouter, HTTPException, Depends
from database import get_database
from audit_service import get_audit_service
from deployment_service import get_deployment_service, DeploymentStage, ApprovalStatus
from authentication_service import get_current_user
from auth_types import TokenData
from tenant_context import get_tenant_id
from rbac_service import rbac_service
import os
from typing import Any

router = APIRouter(tags=["Deployments"])

async def log_audit_event(action, user_id, tenant_id, details):
    service = get_audit_service()
    await service.log_action_async(user_id, action, "deployment", None, str(details), None, tenant_id=tenant_id)

@router.post("/api/deployments/staged")
async def create_staged_deployment(data: dict, current_user: TokenData = Depends(rbac_service.has_permission("view:software_deployment"))):
    """
    Create a new staged deployment with Test → Dev → Staging → Production phases
    """
    try:
        db = get_database()
        deployment_service = get_deployment_service(db)
        tenant_id = get_tenant_id()
        
        deployment = await deployment_service.create_staged_deployment(
            patch_ids=data.get("patch_ids", []),
            asset_ids=data.get("asset_ids", []),
            tenant_id=tenant_id,
            created_by=current_user.username,
            deployment_config=data.get("config")
        )
        
        # Log audit event
        await log_audit_event(
            action="staged_deployment_created",
            user_id=current_user.username,
            tenant_id=tenant_id,
            details={
                "deployment_id": deployment["id"],
                "patch_count": len(data.get("patch_ids", [])),
                "asset_count": len(data.get("asset_ids", []))
            }
        )
        
        return {
            "success": True,
            "deployment": deployment,
            "message": f"Staged deployment {deployment['id']} created. Starting with Test phase."
        }
    except Exception as e:
        print(f"Error creating staged deployment: {e}")
        return {"error": str(e)}, 500


@router.get("/api/deployments/staged/{deployment_id}")
async def get_staged_deployment(deployment_id: str, current_user: TokenData = Depends(rbac_service.has_permission("view:software_deployment"))):
    """Get detailed status of a staged deployment"""
    try:
        db = get_database()
        deployment_service = get_deployment_service(db)
        tenant_id = get_tenant_id()
        
        deployment = await deployment_service.get_deployment(deployment_id)
        
        if not deployment:
            return {"error": "Deployment not found"}, 404
            
        if deployment.get("tenant_id") != tenant_id and deployment.get("tenantId") != tenant_id:
             return {"error": "Unauthorized"}, 403
        
        return deployment
    except Exception as e:
        print(f"Error getting deployment: {e}")
        return {"error": str(e)}, 500


@router.post("/api/deployments/staged/{deployment_id}/progress")
async def update_deployment_progress(deployment_id: str, data: dict, current_user: TokenData = Depends(rbac_service.has_permission("view:software_deployment"))):
    """
    Update progress for an asset in current stage
    """
    try:
        db = get_database()
        deployment_service = get_deployment_service(db)
        tenant_id = get_tenant_id()
        
        deployment = await deployment_service.get_deployment(deployment_id)
        if not deployment:
            return {"error": "Deployment not found"}, 404
        if deployment.get("tenant_id") != tenant_id and deployment.get("tenantId") != tenant_id:
             return {"error": "Unauthorized"}, 403
        
        stage_data = await deployment_service.update_stage_progress(
            deployment_id=deployment_id,
            stage=DeploymentStage(data.get("stage")),
            asset_id=data.get("asset_id"),
            success=data.get("success"),
            details=data.get("details")
        )
        
        return {
            "success": True,
            "stage_data": stage_data
        }
    except Exception as e:
        print(f"Error updating progress: {e}")
        return {"error": str(e)}, 500


@router.post("/api/deployments/approvals/request")
async def request_stage_approval(data: dict, current_user: TokenData = Depends(rbac_service.has_permission("view:software_deployment"))):
    """
    Request approval to proceed to next stage
    """
    try:
        db = get_database()
        deployment_service = get_deployment_service(db)
        tenant_id = get_tenant_id()
        
        deployment_id = data.get("deployment_id")
        deployment = await deployment_service.get_deployment(deployment_id)
        if not deployment:
            return {"error": "Deployment not found"}, 404
        if deployment.get("tenant_id") != tenant_id and deployment.get("tenantId") != tenant_id:
             return {"error": "Unauthorized"}, 403
        
        approval = await deployment_service.request_approval(
            deployment_id=deployment_id,
            stage=DeploymentStage(data.get("stage")),
            approvers=data.get("approvers", [])
        )
        
        return {
            "success": True,
            "approval": approval,
            "message": f"Approval request created. Notified {len(data.get('approvers', []))} approvers."
        }
    except Exception as e:
        print(f"Error requesting approval: {e}")
        return {"error": str(e)}, 500


@router.get("/api/deployments/approvals/pending")
async def get_pending_approvals(current_user: TokenData = Depends(rbac_service.has_permission("view:software_deployment"))):
    """Get all pending approval requests for the current tenant"""
    try:
        db = get_database()
        tenant_id = get_tenant_id()
        
        # We need to filter approvals by deployment's tenant_id
        # This is a bit complex in one query if tenant_id is not in approval doc
        # Let's assume we added tenantId to approvals or we filter after fetch
        
        query = {"status": ApprovalStatus.PENDING}
        # If we want to filter by specific approver:
        # query["approvers"] = current_user.username
        
        approvals = await db.deployment_approvals.find(query, {"_id": 0}).to_list(length=None)
        
        tenant_approvals = []
        # Enrich with deployment details and filter by tenant
        for approval in approvals:
            deployment = await db.staged_deployments.find_one(
                {"id": approval["deployment_id"]},
                {"_id": 0, "patch_ids": 1, "current_stage": 1, "created_by": 1, "tenant_id": 1, "tenantId": 1}
            )
            if deployment and (deployment.get("tenant_id") == tenant_id or deployment.get("tenantId") == tenant_id):
                approval["deployment_info"] = deployment
                tenant_approvals.append(approval)
        
        return {
            "approvals": tenant_approvals,
            "count": len(tenant_approvals)
        }
    except Exception as e:
        print(f"Error getting approvals: {e}")
        return {"error": str(e)}, 500


@router.post("/api/deployments/approvals/{approval_id}/approve")
async def approve_deployment_stage(approval_id: str, data: dict, current_user: TokenData = Depends(rbac_service.has_permission("manage:settings"))):
    """
    Approve a stage and progress deployment
    """
    try:
        db = get_database()
        deployment_service = get_deployment_service(db)
        tenant_id = get_tenant_id()
        
        # Verify ownership via deployment
        approval_doc = await db.deployment_approvals.find_one({"id": approval_id})
        if not approval_doc:
             return {"error": "Approval not found"}, 404
             
        deployment = await deployment_service.get_deployment(approval_doc["deployment_id"])
        if not deployment or (deployment.get("tenant_id") != tenant_id and deployment.get("tenantId") != tenant_id):
             return {"error": "Unauthorized"}, 403
        
        approval = await deployment_service.approve_stage(
            approval_id=approval_id,
            approved_by=current_user.username,
            comments=data.get("comments")
        )
        
        # Log audit event
        await log_audit_event(
            action="deployment_stage_approved",
            user_id=current_user.username,
            tenant_id=tenant_id,
            details={
                "approval_id": approval_id,
                "deployment_id": approval["deployment_id"],
                "stage": approval["stage"]
            }
        )
        
        return {
            "success": True,
            "approval": approval,
            "message": f"Stage {approval['stage']} approved. Deployment progressing to next stage."
        }
    except Exception as e:
        print(f"Error approving stage: {e}")
        return {"error": str(e)}, 500


@router.post("/api/deployments/approvals/{approval_id}/reject")
async def reject_deployment_stage(approval_id: str, data: dict, current_user: TokenData = Depends(rbac_service.has_permission("manage:settings"))):
    """
    Reject a stage and halt deployment
    """
    try:
        db = get_database()
        deployment_service = get_deployment_service(db)
        tenant_id = get_tenant_id()
        
        approval_doc = await db.deployment_approvals.find_one({"id": approval_id})
        if not approval_doc:
             return {"error": "Approval not found"}, 404
             
        deployment = await deployment_service.get_deployment(approval_doc["deployment_id"])
        if not deployment or (deployment.get("tenant_id") != tenant_id and deployment.get("tenantId") != tenant_id):
             return {"error": "Unauthorized"}, 403
        
        approval = await deployment_service.reject_stage(
            approval_id=approval_id,
            rejected_by=current_user.username,
            reason=data.get("reason")
        )
        
        # Log audit event
        await log_audit_event(
            action="deployment_stage_rejected",
            user_id=current_user.username,
            tenant_id=tenant_id,
            details={
                "approval_id": approval_id,
                "deployment_id": approval["deployment_id"],
                "reason": data.get("reason")
            }
        )
        
        return {
            "success": True,
            "approval": approval,
            "message": "Deployment rejected and halted."
        }
    except Exception as e:
        print(f"Error rejecting stage: {e}")
        return {"error": str(e)}, 500


@router.post("/api/deployments/{deployment_id}/rollback")
async def rollback_deployment(deployment_id: str, data: dict, current_user: TokenData = Depends(rbac_service.has_permission("manage:settings"))):
    """
    Manually trigger rollback of a deployment
    """
    try:
        db = get_database()
        deployment_service = get_deployment_service(db)
        tenant_id = get_tenant_id()
        
        deployment = await deployment_service.get_deployment(deployment_id)
        if not deployment or (deployment.get("tenant_id") != tenant_id and deployment.get("tenantId") != tenant_id):
             return {"error": "Unauthorized"}, 403
        
        rollback = await deployment_service.trigger_rollback(
            deployment_id=deployment_id,
            reason=data.get("reason", "Manual rollback requested")
        )
        
        # Log audit event
        await log_audit_event(
            action="deployment_rolled_back",
            user_id=current_user.username,
            tenant_id=tenant_id,
            details={
                "deployment_id": deployment_id,
                "rollback_id": rollback["id"],
                "reason": data.get("reason")
            }
        )
        
        return {
            "success": True,
            "rollback": rollback,
            "message": f"Rollback initiated for {len(rollback['asset_ids'])} assets."
        }
    except Exception as e:
        print(f"Error triggering rollback: {e}")
        return {"error": str(e)}, 500


@router.get("/api/deployments/staged")
async def list_staged_deployments(current_user: TokenData = Depends(rbac_service.has_permission("view:software_deployment")), status: str = None):
    """List all staged deployments for the current tenant"""
    try:
        db = get_database()
        tenant_id = get_tenant_id()
        
        query = {"$or": [{"tenant_id": tenant_id}, {"tenantId": tenant_id}]}
        if status:
            query["status"] = status
        
        deployments = await db.staged_deployments.find(
            query, 
            {"_id": 0}
        ).sort("created_at", -1).limit(50).to_list(length=None)
        
        return {
            "deployments": deployments,
            "count": len(deployments)
        }
    except Exception as e:
        print(f"Error listing deployments: {e}")
        return {"error": str(e)}, 500
