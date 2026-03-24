from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, List
from model_retraining_service import mlops_service
from rbac_utils import require_permission

router = APIRouter(prefix="/api/mlops", tags=["MLOps & Automated Retraining"])

@router.get("/models")
async def get_models(
    current_user: dict = Depends(require_permission("view:ai_systems"))
):
    """
    Get Model Registry.
    """
    return mlops_service.get_models()

@router.get("/history")
async def get_history(
    current_user: dict = Depends(require_permission("view:ai_systems"))
):
    """
    Get Training Job History.
    """
    return mlops_service.get_history()

@router.post("/train")
async def trigger_training(
    request: Dict[str, str],
    current_user: dict = Depends(require_permission("manage:ai_models"))
):
    """
    Trigger a new training job.
    Body: {"model_name": "Phishing Detector", "reason": "Manual Trigger"}
    """
    model_name = request.get("model_name")
    reason = request.get("reason", "Manual Trigger")
    
    if not model_name:
        raise HTTPException(status_code=400, detail="model_name is required")
        
    job_id = await mlops_service.trigger_retraining(model_name, reason)
    return {"job_id": job_id, "status": "Pending", "message": "Training job initiated"}

@router.post("/promote")
async def promote_model(
    request: Dict[str, str],
    current_user: dict = Depends(require_permission("manage:ai_models"))
):
    """
    Promote a model version to Production.
    Body: {"model_id": "model-phishing-v2"}
    """
    model_id = request.get("model_id")
    if not model_id:
        raise HTTPException(status_code=400, detail="model_id is required")
        
    try:
        updated_model = mlops_service.promote_model(model_id)
        return {"status": "success", "model": updated_model}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
