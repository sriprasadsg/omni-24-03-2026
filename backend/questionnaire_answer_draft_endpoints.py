from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from authentication_service import get_current_user
from models import User
from questionnaire_answer_draft_service import (
    draft_answer_for_question,
    list_drafts,
    get_draft,
)
from database import get_database

router = APIRouter(prefix="/api/questionnaire-answer-drafts", tags=["Questionnaire Answer Drafts"])

async def _tenant(user: User = Depends(get_current_user)) -> str:
    if not user.tenant_id:
        raise HTTPException(status_code=400, detail="Tenant ID not found for user")
    return user.tenant_id

@router.post("/generate", response_model=Dict[str, Any])
async def generate_draft_endpoint(
    question_id: str,
    question_text: str,
    user: User = Depends(get_current_user),
    tenant_id: str = Depends(_tenant),
    question_set_id: Optional[str] = None,
) -> Dict[str, Any]:
    # Placeholder: In a real scenario, this might be a background task
    # For now, it's synchronous for simplicity/testing
    draft = await draft_answer_for_question(question_id, question_text, tenant_id, get_database(), question_set_id)
    return draft

@router.get("/", response_model=List[Dict[str, Any]])
async def list_drafts_endpoint(
    tenant_id: str = Depends(_tenant),
) -> List[Dict[str, Any]]:
    return await list_drafts(get_database(), tenant_id)

@router.get("/{draft_id}", response_model=Dict[str, Any])
async def get_draft_endpoint(
    draft_id: str,
    tenant_id: str = Depends(_tenant),
) -> Dict[str, Any]:
    draft = await get_draft(draft_id, tenant_id, get_database())
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft