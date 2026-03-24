from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, List
from xai_service import xai_service
from rbac_utils import require_permission

router = APIRouter(prefix="/api/xai", tags=["AI Explainability (XAI)"])

@router.get("/global/{model_id}")
async def get_global_importance(
    model_id: str,
    current_user: dict = Depends(require_permission("view:ai_systems"))
):
    """
    Get global feature importance for a model.
    """
    return xai_service.get_global_importance(model_id)

@router.post("/explain")
async def explain_prediction(
    request: Dict[str, Any],
    current_user: dict = Depends(require_permission("view:ai_systems"))
):
    """
    Get local explanation (SHAP) for a specific input.
    Body: { "model_id": "...", "input": { ... } }
    """
    model_id = request.get("model_id", "default")
    input_data = request.get("input", {})
    
    return xai_service.explain_prediction(model_id, input_data)
