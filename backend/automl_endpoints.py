from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, List
from automl_service import automl_service
from rbac_utils import require_permission

router = APIRouter(prefix="/api/automl", tags=["AutoML & Hyperparameter Optimization"])

@router.get("/studies")
async def list_studies(
    current_user: dict = Depends(require_permission("view:ai_systems"))
):
    """
    List all optimization studies.
    """
    return automl_service.get_all_studies()

@router.post("/study")
async def create_study(
    request: Dict[str, str],
    current_user: dict = Depends(require_permission("manage:ai_models"))
):
    """
    Create a new study.
    Body: {"name": "Optimize CNN"}
    """
    name = request.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
        
    study_id = automl_service.create_study(name)
    return {"study_id": study_id, "message": "Study created"}

@router.get("/study/{study_id}")
async def get_study_details(
    study_id: str,
    current_user: dict = Depends(require_permission("view:ai_systems"))
):
    """
    Get full details of a study including all trials.
    """
    study = automl_service.get_study(study_id)
    if not study:
        raise HTTPException(status_code=404, detail="Study not found")
    return study

@router.post("/study/{study_id}/run")
async def run_trials(
    study_id: str,
    request: Dict[str, int],
    current_user: dict = Depends(require_permission("manage:ai_models"))
):
    """
    Trigger trials for a study.
    Body: {"n_trials": 10}
    """
    n_trials = request.get("n_trials", 5)
    try:
        count = await automl_service.run_trials(study_id, n_trials)
        return {"message": f"Completed {n_trials} trials", "total_trials": count}
    except ValueError:
        raise HTTPException(status_code=404, detail="Study not found")
