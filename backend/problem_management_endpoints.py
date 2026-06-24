"""ITIL Problem Management API endpoints."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from authentication_service import TokenData
from rbac_service import rbac_service
from problem_management_service import problem_service

from auth_roles import SUPER_ROLES as _SUPER_ROLES

router = APIRouter(prefix="/api/problems", tags=["Problem Management"])


# ── Helpers ───────────────────────────────────────────────────────────────────


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

class CreateProblemRequest(BaseModel):
    title:               str            = Field(..., max_length=500)
    description:         Optional[str]  = ""
    status:              Optional[str]  = "open"
    priority:            Optional[str]  = "medium"
    root_cause:          Optional[str]  = ""
    workaround:          Optional[str]  = ""
    permanent_fix:       Optional[str]  = ""
    linked_incident_ids: Optional[List[str]] = []
    known_error:         Optional[bool] = False
    assignee:            Optional[str]  = ""


class UpdateProblemRequest(BaseModel):
    title:         Optional[str]  = None
    description:   Optional[str]  = None
    status:        Optional[str]  = None
    priority:      Optional[str]  = None
    root_cause:    Optional[str]  = None
    workaround:    Optional[str]  = None
    permanent_fix: Optional[str]  = None
    assignee:      Optional[str]  = None
    known_error:   Optional[bool] = None


class LinkIncidentRequest(BaseModel):
    incident_id: str


class PromoteKnownErrorRequest(BaseModel):
    workaround: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_problems(
    status:       Optional[str] = Query(None),
    priority:     Optional[str] = Query(None),
    page:         int           = Query(1, ge=1),
    page_size:    int           = Query(50, ge=1, le=200),
    current_user: TokenData     = Depends(rbac_service.has_permission("view:security")),
) -> Dict[str, Any]:
    return await problem_service.list_problems(
        tenant_id=_tenant(current_user),
        status=status,
        priority=priority,
        page=page,
        page_size=page_size,
    )


@router.post("")
async def create_problem(
    body:         CreateProblemRequest,
    current_user: TokenData = Depends(rbac_service.has_permission("manage:security")),
) -> Dict[str, Any]:
    tenant_id = _tenant(current_user)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context")
    try:
        return await problem_service.create_problem(
            data=body.model_dump(exclude_none=False),
            reporter=_actor(current_user),
            tenant_id=tenant_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{problem_id}")
async def get_problem(
    problem_id:   str,
    current_user: TokenData = Depends(rbac_service.has_permission("view:security")),
) -> Dict[str, Any]:
    tenant_id = _tenant(current_user)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context")
    doc = await problem_service.get_problem(problem_id, tenant_id=tenant_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Problem not found")
    return doc


@router.patch("/{problem_id}")
async def update_problem(
    problem_id:   str,
    body:         UpdateProblemRequest,
    current_user: TokenData = Depends(rbac_service.has_permission("manage:security")),
) -> Dict[str, Any]:
    tenant_id = _tenant(current_user)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context")
    updated = await problem_service.update_problem(
        problem_id,
        data={k: v for k, v in body.model_dump().items() if v is not None},
        actor=_actor(current_user),
        tenant_id=tenant_id,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Problem not found")
    return updated


@router.post("/{problem_id}/link-incident")
async def link_incident(
    problem_id:   str,
    body:         LinkIncidentRequest,
    current_user: TokenData = Depends(rbac_service.has_permission("manage:security")),
) -> Dict[str, Any]:
    tenant_id = _tenant(current_user)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context")
    updated = await problem_service.link_incident(
        problem_id,
        incident_id=body.incident_id,
        tenant_id=tenant_id,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Problem not found")
    return updated


@router.post("/{problem_id}/promote-known-error")
async def promote_known_error(
    problem_id:   str,
    body:         PromoteKnownErrorRequest,
    current_user: TokenData = Depends(rbac_service.has_permission("manage:security")),
) -> Dict[str, Any]:
    tenant_id = _tenant(current_user)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context")
    updated = await problem_service.promote_to_known_error(
        problem_id,
        workaround=body.workaround,
        tenant_id=tenant_id,
        actor=_actor(current_user),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Problem not found")
    return updated
