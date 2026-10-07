from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any, Optional
from training_service import training_service, TrainingModule, UserTrainingProgress
from pydantic import BaseModel
from authentication_service import get_current_user
from auth_types import TokenData
from rbac_utils import require_permission

router = APIRouter(prefix="/api/training", tags=["Security Awareness Training"])

class ModuleCreate(BaseModel):
    title: str
    description: str
    content_url: str
    duration_minutes: int
    quiz_questions: List[Dict[str, Any]]

class AssignmentCreate(BaseModel):
    user_email: str
    module_id: str

class ProgressUpdate(BaseModel):
    status: Optional[str] = None
    quiz_score: Optional[int] = None

@router.get("/modules", response_model=List[TrainingModule])
def get_modules(current_user: TokenData = Depends(get_current_user)):
    return training_service.get_modules()

@router.post("/modules", response_model=TrainingModule)
def create_module(module: ModuleCreate, current_user: TokenData = Depends(require_permission("manage:settings"))):
    return training_service.create_module(module.dict())

@router.post("/assign", response_model=UserTrainingProgress)
def assign_training(assignment: AssignmentCreate, current_user: TokenData = Depends(require_permission("manage:settings"))):
    return training_service.assign_training(assignment.user_email, assignment.module_id)

@router.get("/my-training", response_model=List[Dict[str, Any]])
def get_my_training(current_user: TokenData = Depends(get_current_user)):
    return training_service.get_user_training(current_user.username)

@router.put("/progress/{assignment_id}", response_model=UserTrainingProgress)
def update_progress(assignment_id: str, updates: ProgressUpdate, current_user: TokenData = Depends(get_current_user)):
    # Users may only update their own assignments
    assignment = next((a for a in training_service.assignments if a.id == assignment_id), None)
    if not assignment or assignment.user_email != current_user.username:
        raise HTTPException(status_code=404, detail="Assignment not found")
    result = training_service.update_progress(assignment_id, updates.dict(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return result
