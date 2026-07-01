"""
Incident War Room Endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Body, Query
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
import logging

from authentication_service import get_current_user
from auth_types import TokenData
import incident_warroom_service as svc


class CreateIncidentRequest(BaseModel):
    title: str
    description: Optional[str] = None
    severity: Optional[str] = None
    incident_type: Optional[str] = None
    affected_assets: Optional[List[str]] = None
    tags: Optional[List[str]] = None

router = APIRouter(prefix="/api/incidents", tags=["Incident War Room"])
logger = logging.getLogger(__name__)


@router.get("/summary")
async def get_summary(current_user: TokenData = Depends(get_current_user)):
    return await svc.get_incident_summary(current_user.tenant_id or "", current_user.role or "")


@router.get("")
async def list_incidents(
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    current_user: TokenData = Depends(get_current_user),
):
    incidents = await svc.list_incidents(
        current_user.tenant_id or "",
        current_user.role or "",
        status=status,
        limit=limit,
    )
    return {"incidents": incidents, "total": len(incidents)}


@router.post("")
async def create_incident(
    payload: CreateIncidentRequest,
    current_user: TokenData = Depends(get_current_user),
):
    if payload.severity and payload.severity not in svc.INCIDENT_SEVERITIES:
        raise HTTPException(status_code=400, detail=f"Invalid severity. Choose from: {svc.INCIDENT_SEVERITIES}")

    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    incident = await svc.create_incident(
        current_user.tenant_id,
        current_user.username or "",
        payload.dict(exclude_none=True),
    )
    incident.pop("_id", None)
    return {"incident": incident, "message": "Incident created — war room is now active"}


@router.get("/{incident_id}")
async def get_incident(incident_id: str, current_user: TokenData = Depends(get_current_user)):
    inc = await svc.get_incident(incident_id, current_user.tenant_id or "", current_user.role or "")
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {"incident": inc}


@router.put("/{incident_id}/status")
async def update_status(
    incident_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    new_status = payload.get("status", "")
    if new_status not in svc.INCIDENT_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Choose from: {svc.INCIDENT_STATUSES}")

    success = await svc.update_incident_status(
        incident_id=incident_id,
        actor=current_user.username or "",
        new_status=new_status,
        tenant_id=current_user.tenant_id or "",
        role=current_user.role or "",
        note=payload.get("note", ""),
    )
    if not success:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {"message": f"Incident status updated to {new_status}"}


@router.post("/{incident_id}/timeline")
async def add_timeline_event(
    incident_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    entry = await svc.add_timeline_event(
        incident_id, current_user.username or "", current_user.tenant_id or "", current_user.role or "", payload
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {"entry": entry}


@router.post("/{incident_id}/tasks")
async def add_task(
    incident_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    task = await svc.add_task(
        incident_id, current_user.username or "", current_user.tenant_id or "", current_user.role or "", payload
    )
    if not task:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {"task": task}


@router.post("/{incident_id}/chat")
async def post_chat(
    incident_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    message = payload.get("message", "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    msg = await svc.add_chat_message(
        incident_id, current_user.username or "", current_user.tenant_id or "", current_user.role or "", message
    )
    if not msg:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {"message": msg}
