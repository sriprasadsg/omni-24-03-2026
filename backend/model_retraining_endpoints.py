from fastapi import APIRouter, HTTPException, Depends
from typing import Dict
from model_retraining_service import mlops_service
from rbac_utils import require_permission

router = APIRouter(prefix="/api/mlops", tags=["MLOps & Automated Retraining"])

@router.get("/models")
async def get_models(current_user: dict = Depends(require_permission("view:mlops"))):
    """Get Model Registry."""
    tenant_id = getattr(current_user, "tenant_id", None) or getattr(current_user, "tenantId", None)
    return await mlops_service.get_models(tenant_id)

@router.get("/history")
async def get_history(current_user: dict = Depends(require_permission("view:mlops"))):
    """Get Training Job History."""
    tenant_id = getattr(current_user, "tenant_id", None) or getattr(current_user, "tenantId", None)
    return await mlops_service.get_history(tenant_id)

@router.post("/train")
async def trigger_training(
    request: Dict[str, str],
    current_user: dict = Depends(require_permission("manage:ai"))
):
    """Trigger a new training job. Body: {"model_name": "...", "reason": "..."}"""
    model_name = request.get("model_name")
    reason = request.get("reason", "Manual Trigger")
    if not model_name:
        raise HTTPException(status_code=400, detail="model_name is required")
    tenant_id = getattr(current_user, "tenant_id", None) or getattr(current_user, "tenantId", None)
    job_id = await mlops_service.trigger_retraining(model_name, reason, tenant_id)
    return {"job_id": job_id, "status": "Pending", "message": "Training job initiated"}

@router.post("/promote")
async def promote_model(
    request: Dict[str, str],
    current_user: dict = Depends(require_permission("manage:ai"))
):
    """Promote a model version to Production. Body: {"model_id": "..."}"""
    model_id = request.get("model_id")
    if not model_id:
        raise HTTPException(status_code=400, detail="model_id is required")
    tenant_id = getattr(current_user, "tenant_id", None) or getattr(current_user, "tenantId", None)
    try:
        updated_model = await mlops_service.promote_model(model_id, tenant_id)
        return {"status": "success", "model": updated_model}
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")
