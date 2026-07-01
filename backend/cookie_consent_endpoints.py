"""Cookie Consent Management endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Request
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from authentication_service import get_current_user
from auth_types import TokenData
from cookie_consent_service import cookie_consent_service

router = APIRouter(prefix="/api/cookie-consent", tags=["Cookie Consent"])


def _tenant(user: TokenData) -> str:
    tid = getattr(user, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return tid


def _role(user: TokenData) -> str:
    return getattr(user, "role", "")


class ConfigUpdate(BaseModel):
    categories: Optional[List[Dict[str, Any]]] = None
    version: Optional[str] = None
    bannerTitle: Optional[str] = None
    bannerText: Optional[str] = None
    privacyPolicyUrl: Optional[str] = None


class ConsentRecord(BaseModel):
    tenantId: str
    sessionId: str
    consentedCategories: List[str]
    userId: Optional[str] = None


@router.get("/config")
async def get_config(tenant_id: str, current_user: TokenData = Depends(get_current_user)):
    """Get the cookie consent configuration for a tenant."""
    return await cookie_consent_service.get_config(tenant_id or _tenant(current_user))


@router.put("/config")
async def update_config(payload: ConfigUpdate, current_user: TokenData = Depends(get_current_user)):
    return await cookie_consent_service.update_config(
        _tenant(current_user), payload.model_dump(exclude_none=True)
    )


@router.post("/record")
async def record_consent(payload: ConsentRecord, request: Request):
    """Public endpoint — records visitor cookie consent. No auth required."""
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")
    meta = {"userId": payload.userId, "ipAddress": ip, "userAgent": ua}
    return await cookie_consent_service.record_consent(
        payload.tenantId, payload.sessionId, payload.consentedCategories, meta
    )


@router.get("/session/{tenant_id}/{session_id}")
async def get_session_consent(tenant_id: str, session_id: str):
    """Public endpoint — retrieve stored consent for a session."""
    result = await cookie_consent_service.get_consent_for_session(tenant_id, session_id)
    if not result:
        return {"consentedCategories": [], "recorded": False}
    return {**result, "recorded": True}


@router.get("/records")
async def get_records(current_user: TokenData = Depends(get_current_user)):
    return await cookie_consent_service.get_records(_tenant(current_user), _role(current_user))


@router.get("/stats")
async def get_stats(current_user: TokenData = Depends(get_current_user)):
    return await cookie_consent_service.get_stats(_tenant(current_user))
