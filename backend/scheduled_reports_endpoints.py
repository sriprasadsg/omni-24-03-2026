"""
Scheduled Report Delivery Endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Body
from typing import Any, Dict
import logging

from auth_utils import get_current_user
import scheduled_reports_service as svc

router = APIRouter(prefix="/api/reports/scheduled", tags=["Scheduled Reports"])
logger = logging.getLogger(__name__)


def _tid(user) -> str:
    if isinstance(user, dict):
        tid = user.get("tenant_id") or user.get("tenantId") or None
    else:
        tid = getattr(user, "tenant_id", None) or None
    if not tid:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Tenant context required")
    return tid


def _role(user) -> str:
    if isinstance(user, dict):
        return user.get("role", "") or ""
    return getattr(user, "role", "") or ""


def _actor(user) -> str:
    if isinstance(user, dict):
        return user.get("email", "") or user.get("username", "") or ""
    return getattr(user, "username", "") or ""


@router.get("/types")
async def list_report_types(current_user=Depends(get_current_user)):
    return {
        "report_types": [{"id": k, **v} for k, v in svc.REPORT_TYPES.items()],
        "frequencies": svc.SCHEDULE_FREQUENCIES,
        "delivery_channels": svc.DELIVERY_CHANNELS,
    }


@router.get("")
async def list_schedules(current_user=Depends(get_current_user)):
    schedules = await svc.list_schedules(_tid(current_user), _role(current_user))
    return {"schedules": schedules, "total": len(schedules)}


@router.post("")
async def create_schedule(
    payload: Dict[str, Any] = Body(...),
    current_user=Depends(get_current_user),
):
    try:
        schedule = await svc.create_schedule(_tid(current_user), _actor(current_user), payload)
        schedule.pop("_id", None)
        return {"schedule": schedule, "message": f"Report scheduled — next delivery: {schedule['next_run'][:10]}"}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.put("/{schedule_id}")
async def update_schedule(
    schedule_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user=Depends(get_current_user),
):
    success = await svc.update_schedule(schedule_id, _tid(current_user), _role(current_user), payload)
    if not success:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"message": "Schedule updated"}


@router.delete("/{schedule_id}")
async def delete_schedule(
    schedule_id: str,
    current_user=Depends(get_current_user),
):
    success = await svc.delete_schedule(schedule_id, _tid(current_user), _role(current_user))
    if not success:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"message": "Schedule deleted"}


@router.get("/{schedule_id}/history")
async def get_delivery_history(schedule_id: str, current_user=Depends(get_current_user)):
    logs = await svc.get_delivery_history(schedule_id, _tid(current_user), _role(current_user))
    return {"logs": logs, "total": len(logs)}


# Canonical route: POST /{schedule_id}/run-now — frontend must call /run-now not /run
@router.post("/{schedule_id}/run-now")
async def run_now(schedule_id: str, current_user=Depends(get_current_user)):
    try:
        result = await svc.run_report_now(schedule_id, _tid(current_user), _role(current_user))
        return result
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")
