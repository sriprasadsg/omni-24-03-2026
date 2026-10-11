from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import training_service
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData
from rbac_utils import require_permission

router = APIRouter(prefix="/api/training", tags=["Security Awareness Training"])


class QuizQuestion(BaseModel):
    question: str = Field(..., max_length=1000)
    options: List[str] = Field(..., max_length=10)
    correct_answer: str


class ModuleCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field("", max_length=4000)
    content_url: str = Field("", max_length=2000)
    duration_minutes: int = Field(0, ge=0, le=1440)
    quiz_questions: List[QuizQuestion] = Field(default_factory=list, max_length=50)


class AssignmentCreate(BaseModel):
    user_email: str = Field(..., max_length=254)
    module_id: str


class ProgressUpdate(BaseModel):
    # A score can only come from POST /progress/{id}/quiz, never from the client
    status: Optional[str] = None


class QuizSubmission(BaseModel):
    answers: List[str] = Field(..., max_length=50)


@router.get("/modules")
async def get_modules(current_user: TokenData = Depends(get_current_user)):
    return await training_service.list_modules(get_database())


@router.post("/modules")
async def create_module(module: ModuleCreate, current_user: TokenData = Depends(require_permission("manage:settings"))):
    data = module.model_dump()
    error = training_service.validate_quiz(data["quiz_questions"])
    if error:
        raise HTTPException(status_code=400, detail=error)
    return await training_service.create_module(get_database(), data)


@router.post("/assign")
async def assign_training(assignment: AssignmentCreate, current_user: TokenData = Depends(require_permission("manage:settings"))):
    db = get_database()
    if not await training_service.get_module(db, assignment.module_id):
        raise HTTPException(status_code=404, detail="Module not found")
    return await training_service.assign(db, assignment.user_email, assignment.module_id)


@router.get("/assignments", response_model=List[Dict[str, Any]])
async def get_assignments(current_user: TokenData = Depends(require_permission("manage:settings"))):
    return await training_service.all_assignments(get_database())


@router.get("/my-training", response_model=List[Dict[str, Any]])
async def get_my_training(current_user: TokenData = Depends(get_current_user)):
    return await training_service.user_training(get_database(), current_user.username)


async def _own_assignment(db, assignment_id: str, current_user: TokenData) -> Dict[str, Any]:
    # Users may only act on their own assignments
    assignment = await training_service.get_assignment(db, assignment_id)
    if not assignment or assignment["user_email"] != (current_user.username or "").strip().lower():
        raise HTTPException(status_code=404, detail="Assignment not found")
    return assignment


@router.put("/progress/{assignment_id}")
async def update_progress(assignment_id: str, updates: ProgressUpdate, current_user: TokenData = Depends(get_current_user)):
    db = get_database()
    assignment = await _own_assignment(db, assignment_id, current_user)
    if updates.status == "In Progress":
        return await training_service.start(db, assignment)
    if updates.status == "Completed":
        module = await training_service.get_module(db, assignment["module_id"])
        if module and module.get("quiz_questions"):
            raise HTTPException(status_code=400, detail="This module is completed by passing its quiz")
        return await training_service.complete_without_quiz(db, assignment)
    raise HTTPException(status_code=400, detail="status must be 'In Progress' or 'Completed'")


@router.post("/progress/{assignment_id}/quiz")
async def submit_quiz(assignment_id: str, submission: QuizSubmission, current_user: TokenData = Depends(get_current_user)):
    db = get_database()
    assignment = await _own_assignment(db, assignment_id, current_user)
    module = await training_service.get_module(db, assignment["module_id"])
    if not module or not module.get("quiz_questions"):
        raise HTTPException(status_code=400, detail="This module has no quiz")
    return await training_service.submit_quiz(db, assignment, module, submission.answers)
