"""Maturity Level Scoring endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from pydantic import BaseModel
from authentication_service import get_current_user
from auth_types import TokenData
from maturity_service import maturity_service

router = APIRouter(prefix="/api/maturity", tags=["Maturity Assessment"])


def _tenant(user: TokenData) -> str:
    tid = getattr(user, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return tid


def _role(user: TokenData) -> str:
    return getattr(user, "role", "")


class AssessmentPayload(BaseModel):
    domain: str
    framework: Optional[str] = "General"
    level: int
    evidence: Optional[str] = None
    notes: Optional[str] = None
    targetLevel: Optional[int] = None


@router.get("/domains")
async def get_domains():
    return {"domains": await maturity_service.get_domains()}


@router.get("/summary")
async def get_summary(
    framework: Optional[str] = Query(None),
    current_user: TokenData = Depends(get_current_user),
):
    return await maturity_service.get_summary(_tenant(current_user), _role(current_user), framework)


@router.get("/gaps")
async def get_gaps(
    framework: Optional[str] = Query(None),
    current_user: TokenData = Depends(get_current_user),
):
    return await maturity_service.get_gaps(_tenant(current_user), _role(current_user), framework)


@router.get("")
async def list_assessments(
    framework: Optional[str] = Query(None),
    current_user: TokenData = Depends(get_current_user),
):
    return await maturity_service.list_assessments(_tenant(current_user), _role(current_user), framework)


@router.post("")
async def upsert_assessment(payload: AssessmentPayload, current_user: TokenData = Depends(get_current_user)):
    assessed_by = getattr(current_user, "username", getattr(current_user, "email", "unknown"))
    return await maturity_service.upsert_assessment(
        payload.model_dump(exclude_none=True), _tenant(current_user), assessed_by
    )


@router.get("/history/{domain}")
async def get_domain_history(domain: str, current_user: TokenData = Depends(get_current_user)):
    return await maturity_service.get_history(domain, _tenant(current_user), _role(current_user))
