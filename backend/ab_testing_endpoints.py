from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Dict, Any, List
from ab_testing_service import ab_service
from rbac_utils import require_permission
from rate_limiter import limiter
from authentication_service import get_current_user

router = APIRouter(prefix="/api/experiments", tags=["A/B Testing & Experimentation"])

@router.get("/")
async def list_experiments(
    current_user: dict = Depends(require_permission("view:system"))
):
    """
    List all active experiments.
    """
    return await ab_service.get_all_experiments()

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
        
    exp_id = await ab_service.create_experiment(name, desc, variants)
    return {"experiment_id": exp_id, "message": "Experiment created"}

@router.get("/{experiment_id}/variant")
@limiter.limit("20/minute")
async def get_variant(
    request: Request,
    experiment_id: str,
    user_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Get assigned variant for a user.
    """
    if not experiment_id or len(experiment_id) > 100:
        raise HTTPException(status_code=400, detail="Invalid experiment_id")
    if not user_id or len(user_id) > 255:
        raise HTTPException(status_code=400, detail="Invalid user_id")
    try:
        variant = await ab_service.get_variant(experiment_id, user_id)
        return {"variant": variant, "user_id": user_id}
    except ValueError:
        raise HTTPException(status_code=404, detail="Experiment not found")

@router.post("/{experiment_id}/track")
@limiter.limit("30/minute")
async def track_conversion(
    request: Request,
    experiment_id: str,
    body: Dict[str, str],
    current_user: dict = Depends(get_current_user),
):
    """
    Track a conversion event.
    Body: { "user_id": "..." }
    """
    if not experiment_id or len(experiment_id) > 100:
        raise HTTPException(status_code=400, detail="Invalid experiment_id")
    user_id = body.get("user_id")
    if not user_id or len(user_id) > 255:
        raise HTTPException(status_code=400, detail="user_id is required")

    try:
        await ab_service.track_conversion(experiment_id, user_id)
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
        return await ab_service.get_results(experiment_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Experiment not found")
