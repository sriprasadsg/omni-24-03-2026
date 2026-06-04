"""ITIL Change Management API endpoints."""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from authentication_service import TokenData
from rbac_service import rbac_service
from change_management_service import change_service

router = APIRouter(prefix="/api/changes", tags=["Change Management"])


# ── Helpers ───────────────────────────────────────────────────────────────────

_SUPER_ROLES = {"Super Admin", "superadmin", "super_admin", "platform-admin"}


def _actor(user: TokenData) -> str:
    return user.username or "unknown"


def _tenant(user: TokenData) -> str:
    if (user.role or "") in _SUPER_ROLES:
        return ""
    tenant = user.tenant_id or ""
    if not tenant:
        try:
            from tenant_context import get_tenant_id
            tenant = get_tenant_id() or ""
        except Exception:
            pass
    return tenant


# ── Request models ────────────────────────────────────────────────────────────

class CreateChangeRequest(BaseModel):
    title:               str            = Field(..., max_length=500)
    description:         Optional[str]  = ""
    change_type:         Optional[str]  = "normal"
    risk_level:          Optional[str]  = "medium"
    impact_level:        Optional[str]  = "medium"
    risk_assessment:     Optional[str]  = ""
    rollback_plan:       Optional[str]  = ""
    implementation_plan: Optional[str]  = ""
    scheduled_start:     Optional[str]  = None
    scheduled_end:       Optional[str]  = None
    assignee:            Optional[str]  = ""


class UpdateChangeRequest(BaseModel):
    title:               Optional[str] = None
    description:         Optional[str] = None
    change_type:         Optional[str] = None
    risk_level:          Optional[str] = None
    impact_level:        Optional[str] = None
    risk_assessment:     Optional[str] = None
    rollback_plan:       Optional[str] = None
    implementation_plan: Optional[str] = None
    scheduled_start:     Optional[str] = None
    scheduled_end:       Optional[str] = None
    assignee:            Optional[str] = None


class CabVoteRequest(BaseModel):
    vote:   str            = Field(..., pattern="^(approve|reject)$")
    reason: Optional[str]  = ""


class ScheduleChangeRequest(BaseModel):
    scheduled_start: str
    scheduled_end:   str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_changes(
    status:       Optional[str] = Query(None),
    change_type:  Optional[str] = Query(None),
    page:         int           = Query(1, ge=1),
    page_size:    int           = Query(50, ge=1, le=200),
    current_user: TokenData     = Depends(rbac_service.has_permission("view:security")),
) -> Dict[str, Any]:
    return await change_service.list_changes(
        tenant_id=_tenant(current_user),
        status=status,
        change_type=change_type,
        page=page,
        page_size=page_size,
    )


@router.post("")
async def create_change(
    body:         CreateChangeRequest,
    current_user: TokenData = Depends(rbac_service.has_permission("manage:settings")),
) -> Dict[str, Any]:
    tenant_id = _tenant(current_user)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context")
    try:
        return await change_service.create_change(
            data=body.model_dump(exclude_none=False),
            reporter=_actor(current_user),
            tenant_id=tenant_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{change_id}")
async def get_change(
    change_id:    str,
    current_user: TokenData = Depends(rbac_service.has_permission("view:security")),
) -> Dict[str, Any]:
    tenant_id = _tenant(current_user)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context")
    doc = await change_service.get_change(change_id, tenant_id=tenant_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Change request not found")
    return doc


@router.patch("/{change_id}")
async def update_change(
    change_id:    str,
    body:         UpdateChangeRequest,
    current_user: TokenData = Depends(rbac_service.has_permission("manage:settings")),
) -> Dict[str, Any]:
    tenant_id = _tenant(current_user)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context")
    try:
        updated = await change_service.update_change(
            change_id,
            data={k: v for k, v in body.model_dump().items() if v is not None},
            actor=_actor(current_user),
            tenant_id=tenant_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if not updated:
        raise HTTPException(status_code=404, detail="Change request not found")
    return updated


@router.post("/{change_id}/submit-cab")
async def submit_for_cab(
    change_id:    str,
    current_user: TokenData = Depends(rbac_service.has_permission("manage:settings")),
) -> Dict[str, Any]:
    tenant_id = _tenant(current_user)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context")
    updated = await change_service.submit_for_cab(
        change_id,
        tenant_id=tenant_id,
        actor=_actor(current_user),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Change request not found")
    return updated


@router.post("/{change_id}/vote")
async def cast_cab_vote(
    change_id:    str,
    body:         CabVoteRequest,
    current_user: TokenData = Depends(rbac_service.has_permission("view:security")),
) -> Dict[str, Any]:
    tenant_id = _tenant(current_user)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context")
    try:
        updated = await change_service.cast_cab_vote(
            change_id,
            voter=_actor(current_user),
            vote=body.vote,
            reason=body.reason or "",
            tenant_id=tenant_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not updated:
        raise HTTPException(status_code=404, detail="Change request not found")
    return updated


@router.post("/{change_id}/schedule")
async def schedule_change(
    change_id:    str,
    body:         ScheduleChangeRequest,
    current_user: TokenData = Depends(rbac_service.has_permission("manage:settings")),
) -> Dict[str, Any]:
    tenant_id = _tenant(current_user)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context")
    updated = await change_service.schedule_change(
        change_id,
        start=body.scheduled_start,
        end=body.scheduled_end,
        tenant_id=tenant_id,
        actor=_actor(current_user),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Change request not found")
    return updated
