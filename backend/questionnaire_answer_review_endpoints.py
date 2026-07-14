from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from authentication_service import get_current_user
from models import User
from questionnaire_answer_review_service import (
    create_review,
    update_review_decision,
    mark_submitted,
    list_reviews,
    list_pending_drafts,
    QUESTIONNAIRE_ANSWER_REVIEWS_COL,
    QUESTIONNAIRE_ANSWER_DRAFTS_COL,
)
from database import get_database

router = APIRouter(prefix="/api/questionnaire-answer-drafts", tags=["Questionnaire Answer Review"])

# Kept in sync by hand with the equivalent literal in evidence_review_endpoints.py
# and components/QuestionnaireAnswerReviewPanel.tsx (_REVIEWER_ROLES).
# Includes the platform's title-case role names ("Tenant Admin"/"Super Admin",
# assigned at signup/seed) alongside the snake_case variants.
_REVIEWER_ROLES = {"admin", "super_admin", "compliance_reviewer", "Tenant Admin", "Super Admin"}

async def _tenant(user: User = Depends(get_current_user)) -> str:
    if not user.tenant_id:
        raise HTTPException(status_code=400, detail="Tenant ID not found for user")
    return user.tenant_id


def _require_reviewer(user: User) -> None:
    if getattr(user, "role", None) not in _REVIEWER_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Only admins and compliance reviewers can make review decisions",
        )


@router.post("/{draft_id}/review", response_model=Dict[str, Any])
async def create_review_endpoint(
    draft_id: str,
    user: User = Depends(get_current_user),
    tenant_id: str = Depends(_tenant),
) -> Dict[str, Any]:
    review = await create_review(draft_id, get_database(), tenant_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Draft not found or not in pending_review state")
    return review


@router.patch("/{draft_id}/review/{review_id}", response_model=Dict[str, Any])
async def update_review_decision_endpoint(
    draft_id: str,
    review_id: str,
    body: Dict[str, Any],
    user: User = Depends(get_current_user),
    tenant_id: str = Depends(_tenant),
) -> Dict[str, Any]:
    _require_reviewer(user)
    decision = body.get("decision")
    comment = body.get("comment")
    edited_answer_text = body.get("edited_answer_text")
    if not decision:
        raise HTTPException(status_code=400, detail="decision required")
    try:
        draft = await update_review_decision(
            review_id, draft_id, decision, comment, get_database(), tenant_id,
            decided_by=user.username, edited_answer_text=edited_answer_text
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if draft is None:
        raise HTTPException(status_code=404, detail="Review or draft not found, or already decided")
    return draft


@router.post("/{draft_id}/submit", response_model=Dict[str, Any])
async def submit_draft_endpoint(
    draft_id: str,
    user: User = Depends(get_current_user),
    tenant_id: str = Depends(_tenant),
) -> Dict[str, Any]:
    _require_reviewer(user)
    draft = await mark_submitted(draft_id, get_database(), tenant_id, user.username)
    if draft is None:
        raise HTTPException(status_code=409, detail="Draft must be in approved state to submit")
    return draft


@router.get("/{draft_id}/reviews", response_model=List[Dict[str, Any]])
async def list_reviews_endpoint(
    draft_id: str,
    tenant_id: str = Depends(_tenant),
) -> List[Dict[str, Any]]:
    return await list_reviews(draft_id, get_database(), tenant_id)


@router.get("/pending-review", response_model=List[Dict[str, Any]])
async def list_pending_drafts_endpoint(
    tenant_id: str = Depends(_tenant),
) -> List[Dict[str, Any]]:
    return await list_pending_drafts(get_database(), tenant_id)