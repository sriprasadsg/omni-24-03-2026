"""
Incident War Room Endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Body, Query
from typing import Any, Dict, Optional
import logging

from auth_utils import get_current_user
import incident_warroom_service as svc

router = APIRouter(prefix="/api/incidents", tags=["Incident War Room"])
logger = logging.getLogger(__name__)


@router.get("/summary")
async def get_summary(current_user: dict = Depends(get_current_user)):
    return await svc.get_incident_summary(
        current_user.get("tenant_id", ""), current_user.get("role", "")
    )


@router.get("")
async def list_incidents(
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    current_user: dict = Depends(get_current_user),
):
    incidents = await svc.list_incidents(
        current_user.get("tenant_id", ""),
        current_user.get("role", ""),
        status=status,
        limit=limit,
    )
    return {"incidents": incidents, "total": len(incidents)}


@router.post("")
async def create_incident(
    payload: Dict[str, Any] = Body(...),
    current_user: dict = Depends(get_current_user),
):
    if not payload.get("title"):
        raise HTTPException(status_code=400, detail="Incident title is required")
    if payload.get("severity") and payload["severity"] not in svc.INCIDENT_SEVERITIES:
        raise HTTPException(status_code=400, detail=f"Invalid severity. Choose from: {svc.INCIDENT_SEVERITIES}")

    tenant_id = current_user.get("tenant_id", "platform-admin")
    actor = current_user.get("email", current_user.get("username", ""))
    incident = await svc.create_incident(tenant_id, actor, payload)
    incident.pop("_id", None)
    return {"incident": incident, "message": "Incident created — war room is now active"}


@router.get("/{incident_id}")
async def get_incident(incident_id: str, current_user: dict = Depends(get_current_user)):
    inc = await svc.get_incident(
        incident_id, current_user.get("tenant_id", ""), current_user.get("role", "")
    )
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {"incident": inc}


@router.put("/{incident_id}/status")
async def update_status(
    incident_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user: dict = Depends(get_current_user),
):
    new_status = payload.get("status", "")
    if new_status not in svc.INCIDENT_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Choose from: {svc.INCIDENT_STATUSES}")

    success = await svc.update_incident_status(
        incident_id=incident_id,
        actor=current_user.get("email", current_user.get("username", "")),
        new_status=new_status,
        tenant_id=current_user.get("tenant_id", ""),
        role=current_user.get("role", ""),
        note=payload.get("note", ""),
    )
    if not success:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {"message": f"Incident status updated to {new_status}"}


@router.post("/{incident_id}/timeline")
async def add_timeline_event(
    incident_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user: dict = Depends(get_current_user),
):
    actor = current_user.get("email", current_user.get("username", ""))
    entry = await svc.add_timeline_event(
        incident_id, actor, current_user.get("tenant_id", ""), current_user.get("role", ""), payload
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {"entry": entry}


@router.post("/{incident_id}/tasks")
async def add_task(
    incident_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user: dict = Depends(get_current_user),
):
    actor = current_user.get("email", current_user.get("username", ""))
    task = await svc.add_task(
        incident_id, actor, current_user.get("tenant_id", ""), current_user.get("role", ""), payload
    )
    if not task:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {"task": task}


@router.post("/{incident_id}/chat")
async def post_chat(
    incident_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user: dict = Depends(get_current_user),
):
    message = payload.get("message", "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    actor = current_user.get("email", current_user.get("username", ""))
    msg = await svc.add_chat_message(
        incident_id, actor, current_user.get("tenant_id", ""), current_user.get("role", ""), message
    )
    if not msg:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {"message": msg}
