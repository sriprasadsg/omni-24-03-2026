"""
GDPR / CCPA Privacy Module Endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Body, Query
from typing import Any, Dict, Optional
import logging

from auth_utils import get_current_user
import privacy_service as svc

router = APIRouter(prefix="/api/privacy", tags=["Privacy & Compliance"])
logger = logging.getLogger(__name__)


def _tid(user):
    """Extract tenant_id from TokenData or dict."""
    if isinstance(user, dict):
        return user.get("tenant_id") or user.get("tenantId") or None
    return getattr(user, "tenant_id", None) or None


def _role(user) -> str:
    if isinstance(user, dict):
        return user.get("role", "") or ""
    return getattr(user, "role", "") or ""


def _actor(user) -> str:
    if isinstance(user, dict):
        return user.get("email", "") or user.get("username", "") or ""
    return getattr(user, "username", "") or ""


@router.get("/summary")
async def privacy_summary(current_user=Depends(get_current_user)):
    return await svc.get_privacy_summary(_tid(current_user), _role(current_user))


@router.get("/dashboard")
async def privacy_dashboard(current_user=Depends(get_current_user)):
    return await svc.get_privacy_dashboard(_tid(current_user), _role(current_user))


# ── Data Subject Requests ──────────────────────────────────────────────────────

@router.get("/dsr")
async def list_dsrs(
    status: Optional[str] = Query(None),
    current_user=Depends(get_current_user),
):
    dsrs = await svc.list_dsrs(_tid(current_user), _role(current_user), status=status)
    return {"dsrs": dsrs, "total": len(dsrs)}


@router.post("/dsr")
async def create_dsr(
    payload: Dict[str, Any] = Body(...),
    current_user=Depends(get_current_user),
):
    if not payload.get("subject_email") and not payload.get("subject_identifier"):
        raise HTTPException(status_code=400, detail="Subject email or identifier is required")

    try:
        dsr = await svc.create_dsr(_tid(current_user), _actor(current_user), payload)
        dsr.pop("_id", None)
        return {"dsr": dsr, "message": f"DSR {dsr['reference_number']} created — due by {dsr['due_date'][:10]}"}
    except ValueError:
        raise HTTPException(status_code=400, detail="Bad request")


@router.put("/dsr/{dsr_id}/status")
async def update_dsr_status(
    dsr_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user=Depends(get_current_user),
):
    new_status = payload.get("status", "")
    if new_status not in svc.DSR_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Choose from: {svc.DSR_STATUSES}")

    success = await svc.update_dsr_status(
        dsr_id,
        actor=_actor(current_user),
        tenant_id=_tid(current_user),
        role=_role(current_user),
        new_status=new_status,
        note=payload.get("note", ""),
    )
    if not success:
        raise HTTPException(status_code=404, detail="DSR not found")
    return {"message": f"DSR status updated to {new_status}"}


# ── Consent Management ─────────────────────────────────────────────────────────

@router.post("/consent")
async def record_consent(
    payload: Dict[str, Any] = Body(...),
    current_user=Depends(get_current_user),
):
    consent = await svc.record_consent(_tid(current_user), payload)
    consent.pop("_id", None)
    return {"consent": consent}


@router.delete("/consent/{consent_id}")
async def withdraw_consent(consent_id: str, current_user=Depends(get_current_user)):
    success = await svc.withdraw_consent(consent_id, _tid(current_user), _role(current_user))
    if not success:
        raise HTTPException(status_code=404, detail="Consent record not found")
    return {"message": "Consent withdrawn and recorded"}


# ── Processing Activities (ROPA) ───────────────────────────────────────────────

@router.get("/processing-activities")
async def list_processing_activities(current_user=Depends(get_current_user)):
    activities = await svc.list_processing_activities(_tid(current_user), _role(current_user))
    return {"activities": activities, "total": len(activities)}


@router.post("/processing-activities")
async def create_processing_activity(
    payload: Dict[str, Any] = Body(...),
    current_user=Depends(get_current_user),
):
    if not payload.get("name"):
        raise HTTPException(status_code=400, detail="Activity name is required")
    if not payload.get("purpose"):
        raise HTTPException(status_code=400, detail="Processing purpose is required")

    activity = await svc.create_processing_activity(_tid(current_user), _actor(current_user), payload)
    activity.pop("_id", None)
    return {"activity": activity, "message": "Processing activity added to ROPA register"}


# ── Breach Notifications ───────────────────────────────────────────────────────

@router.get("/breaches")
async def list_breaches(current_user=Depends(get_current_user)):
    from database import get_database
    db = get_database()
    tid = _tid(current_user)
    role = _role(current_user)
    query: dict = {} if role in ("super_admin", "Super Admin") else {"tenant_id": tid}
    docs = await db.breach_notifications.find(query, {"_id": 0}).sort("created_at", -1).to_list(length=200)
    return {"breaches": docs, "total": len(docs)}


@router.post("/breaches")
async def report_breach(
    payload: Dict[str, Any] = Body(...),
    current_user=Depends(get_current_user),
):
    if not payload.get("description"):
        raise HTTPException(status_code=400, detail="Breach description is required")

    breach = await svc.create_breach_notification(_tid(current_user), _actor(current_user), payload)
    breach.pop("_id", None)
    return {
        "breach": breach,
        "message": f"Breach {breach['reference']} recorded — GDPR supervisory authority notification deadline: {breach['authority_notification_deadline'][:19]} UTC",
        "warning": "72-hour notification window is active" if payload.get("notification_required", True) else None,
    }
