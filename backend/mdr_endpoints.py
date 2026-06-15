"""
MDR Endpoints â€” Managed Detection & Response REST API.

Routes:
  GET  /api/mdr/dashboard      - KPI summary (active hunts, coverage, threats)
  GET  /api/mdr/metrics        - MTTD / MTTR and SLA breach data
  GET  /api/mdr/sla            - SLA thresholds + breach summary (alias for /metrics)
  GET  /api/mdr/hunts          - list managed threat hunts
  POST /api/mdr/hunts          - create a new managed hunt
  PATCH /api/mdr/hunts/{id}    - update hunt status / findings / notes
  GET  /api/mdr/escalations    - list escalations
  POST /api/mdr/escalations    - create an escalation
  PATCH /api/mdr/escalations/{id} - acknowledge or resolve escalation
  GET  /api/mdr/coverage       - asset coverage breakdown by platform
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from authentication_service import get_current_user
import mdr_service as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mdr", tags=["MDR"])

_SUPER_ADMIN_ROLES = {"Super Admin", "superadmin", "super_admin", "platform-admin"}


def _tenant_filter(user: dict) -> dict:
    if user.get("role") in _SUPER_ADMIN_ROLES:
        return {}
    tenant = user.get("tenantId") or user.get("tenant_id") or ""
    return {"tenantId": tenant} if tenant else {}


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class HuntCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    hypothesis: str = ""
    severity: str = "medium"
    assigned_to: str = ""


class HuntUpdate(BaseModel):
    status: Optional[str] = None
    findings: Optional[list] = None
    notes: Optional[str] = None
    assigned_to: Optional[str] = None
    severity: Optional[str] = None


class EscalationCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    severity: str = "high"
    incident_id: Optional[str] = None
    case_id: Optional[str] = None
    description: str = ""


class EscalationUpdate(BaseModel):
    status: str
    resolution_notes: str = ""


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/dashboard")
async def get_dashboard(current_user: dict = Depends(get_current_user)):
    tf = _tenant_filter(current_user)
    return await svc.get_dashboard_summary(tf)


@router.get("/metrics")
async def get_metrics(
    window_hours: int = Query(168, ge=1, le=8760),
    current_user: dict = Depends(get_current_user),
):
    tf = _tenant_filter(current_user)
    return await svc.compute_sla_metrics(tf, window_hours=window_hours)


@router.get("/sla")
async def get_sla(
    window_hours: int = Query(168, ge=1, le=8760),
    current_user: dict = Depends(get_current_user),
):
    tf = _tenant_filter(current_user)
    return await svc.compute_sla_metrics(tf, window_hours=window_hours)


@router.get("/hunts")
async def list_hunts(
    status: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    tf = _tenant_filter(current_user)
    return await svc.list_hunts(tf, status=status)


@router.post("/hunts", status_code=201)
async def create_hunt(
    body: HuntCreate,
    current_user: dict = Depends(get_current_user),
):
    tf = _tenant_filter(current_user)
    return await svc.create_hunt(
        body.model_dump(),
        tenant_filter=tf,
        created_by=current_user.get("email") or current_user.get("username") or "unknown",
    )


@router.patch("/hunts/{hunt_id}")
async def update_hunt(
    hunt_id: str,
    body: HuntUpdate,
    current_user: dict = Depends(get_current_user),
):
    tf = _tenant_filter(current_user)
    result = await svc.update_hunt(hunt_id, body.model_dump(exclude_none=True), tf)
    if result is None:
        raise HTTPException(status_code=404, detail="Hunt not found")
    return result


@router.get("/escalations")
async def list_escalations(
    status: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    tf = _tenant_filter(current_user)
    return await svc.list_escalations(tf, status=status)


@router.post("/escalations", status_code=201)
async def create_escalation(
    body: EscalationCreate,
    current_user: dict = Depends(get_current_user),
):
    tf = _tenant_filter(current_user)
    return await svc.create_escalation(
        body.model_dump(),
        tenant_filter=tf,
        escalated_by=current_user.get("email") or current_user.get("username") or "unknown",
    )


@router.patch("/escalations/{esc_id}")
async def update_escalation(
    esc_id: str,
    body: EscalationUpdate,
    current_user: dict = Depends(get_current_user),
):
    tf = _tenant_filter(current_user)
    result = await svc.update_escalation(esc_id, body.model_dump(), tf)
    if result is None:
        raise HTTPException(status_code=404, detail="Escalation not found")
    return result


@router.get("/coverage")
async def get_coverage(current_user: dict = Depends(get_current_user)):
    tf = _tenant_filter(current_user)
    return await svc.get_coverage(tf)

