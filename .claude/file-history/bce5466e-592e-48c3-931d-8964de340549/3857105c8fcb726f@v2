"""Periodic Access Review endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from authentication_service import get_current_user
from auth_types import TokenData
from access_review_service import access_review_service

router = APIRouter(prefix="/api/access-reviews", tags=["Access Reviews"])


def _tenant(user: TokenData) -> str:
    tid = getattr(user, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return tid


def _role(user: TokenData) -> str:
    return getattr(user, "role", "")


class ReviewCreate(BaseModel):
    name: str
    description: Optional[str] = None
    type: Optional[str] = "User Access"
    frequency: Optional[str] = "Quarterly"
    reviewer: Optional[str] = None
    nextReviewDate: Optional[str] = None
    scopeUsers: Optional[List[Dict[str, Any]]] = None


class DecisionItem(BaseModel):
    userId: str
    userName: Optional[str] = None
    decision: str
    reason: Optional[str] = None


class DecisionsPayload(BaseModel):
    decisions: List[DecisionItem]


@router.get("/summary")
async def get_summary(current_user: TokenData = Depends(get_current_user)):
    return await access_review_service.get_summary(_tenant(current_user), _role(current_user))


@router.get("/upcoming")
async def get_upcoming(days: int = Query(30, ge=1, le=365), current_user: TokenData = Depends(get_current_user)):
    return await access_review_service.get_upcoming(_tenant(current_user), _role(current_user), days)


@router.get("")
async def list_reviews(
    status: Optional[str] = Query(None),
    current_user: TokenData = Depends(get_current_user),
):
    return await access_review_service.list_reviews(_tenant(current_user), _role(current_user), status)


@router.post("")
async def create_review(payload: ReviewCreate, current_user: TokenData = Depends(get_current_user)):
    created_by = getattr(current_user, "username", getattr(current_user, "email", "unknown"))
    return await access_review_service.create_review(
        payload.model_dump(exclude_none=True), _tenant(current_user), created_by
    )


@router.get("/{review_id}")
async def get_review(review_id: str, current_user: TokenData = Depends(get_current_user)):
    r = await access_review_service.get_review(review_id, _tenant(current_user), _role(current_user))
    if not r:
        raise HTTPException(status_code=404, detail="Access review not found")
    return r


@router.post("/{review_id}/start")
async def start_review(review_id: str, current_user: TokenData = Depends(get_current_user)):
    r = await access_review_service.start_review(review_id, _tenant(current_user), _role(current_user))
    if not r:
        raise HTTPException(status_code=404, detail="Access review not found or not in Scheduled/Overdue state")
    return r


@router.put("/{review_id}/decisions")
async def submit_decisions(
    review_id: str,
    payload: DecisionsPayload,
    current_user: TokenData = Depends(get_current_user),
):
    r = await access_review_service.submit_decisions(
        review_id,
        [d.model_dump() for d in payload.decisions],
        _tenant(current_user),
        _role(current_user),
    )
    if not r:
        raise HTTPException(status_code=404, detail="Access review not found")
    return r


@router.put("/{review_id}/complete")
async def complete_review(review_id: str, current_user: TokenData = Depends(get_current_user)):
    r = await access_review_service.complete_review(review_id, _tenant(current_user), _role(current_user))
    if not r:
        raise HTTPException(status_code=404, detail="Access review not found")
    return r


@router.delete("/{review_id}")
async def delete_review(review_id: str, current_user: TokenData = Depends(get_current_user)):
    deleted = await access_review_service.delete_review(review_id, _tenant(current_user), _role(current_user))
    if not deleted:
        raise HTTPException(status_code=404, detail="Access review not found")
    return {"success": True}
