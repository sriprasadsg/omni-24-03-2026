from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, List
from ab_testing_service import ab_service
from rbac_utils import require_permission

router = APIRouter(prefix="/api/experiments", tags=["A/B Testing & Experimentation"])

@router.get("/")
async def list_experiments(
    current_user: dict = Depends(require_permission("view:system"))
):
    """
    List all active experiments.
    """
    return ab_service.get_all_experiments()

@router.post("/")
async def create_experiment(
    request: Dict[str, Any],
    current_user: dict = Depends(require_permission("manage:system"))
):
    """
    Create a new A/B test.
    Body: { "name": "...", "description": "...", "variants": ["A", "B"] }
    """
    name = request.get("name")
    desc = request.get("description", "")
    variants = request.get("variants", ["Control", "Treatment"])
    
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
        
    exp_id = ab_service.create_experiment(name, desc, variants)
    return {"experiment_id": exp_id, "message": "Experiment created"}

@router.get("/{experiment_id}/variant")
async def get_variant(
    experiment_id: str,
    user_id: str,
    # No permission required, public for client apps
):
    """
    Get assigned variant for a user.
    """
    try:
        variant = ab_service.get_variant(experiment_id, user_id)
        return {"variant": variant, "user_id": user_id}
    except ValueError:
        raise HTTPException(status_code=404, detail="Experiment not found")

@router.post("/{experiment_id}/track")
async def track_conversion(
    experiment_id: str,
    request: Dict[str, str],
    # No permission required, public for client apps
):
    """
    Track a conversion event.
    Body: { "user_id": "..." }
    """
    user_id = request.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
        
    try:
        ab_service.track_conversion(experiment_id, user_id)
        return {"status": "tracked"}
    except ValueError:
        raise HTTPException(status_code=404, detail="Experiment not found")

@router.get("/{experiment_id}/results")
async def get_results(
    experiment_id: str,
    current_user: dict = Depends(require_permission("view:reporting"))
):
    """
    Get performance metrics for an experiment.
    """
    try:
        return ab_service.get_results(experiment_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Experiment not found")
