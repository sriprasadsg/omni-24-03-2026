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


@router.get("/types")
async def list_report_types(current_user: dict = Depends(get_current_user)):
    return {
        "report_types": [{"id": k, **v} for k, v in svc.REPORT_TYPES.items()],
        "frequencies": svc.SCHEDULE_FREQUENCIES,
        "delivery_channels": svc.DELIVERY_CHANNELS,
    }


@router.get("")
async def list_schedules(current_user: dict = Depends(get_current_user)):
    schedules = await svc.list_schedules(
        current_user.get("tenant_id", ""), current_user.get("role", "")
    )
    return {"schedules": schedules, "total": len(schedules)}


@router.post("")
async def create_schedule(
    payload: Dict[str, Any] = Body(...),
    current_user: dict = Depends(get_current_user),
):
    try:
        tenant_id = current_user.get("tenant_id", "platform-admin")
        created_by = current_user.get("email", current_user.get("username", ""))
        schedule = await svc.create_schedule(tenant_id, created_by, payload)
        schedule.pop("_id", None)
        return {"schedule": schedule, "message": f"Report scheduled — next delivery: {schedule['next_run'][:10]}"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/{schedule_id}")
async def update_schedule(
    schedule_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user: dict = Depends(get_current_user),
):
    success = await svc.update_schedule(
        schedule_id, current_user.get("tenant_id", ""), current_user.get("role", ""), payload
    )
    if not success:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"message": "Schedule updated"}


@router.delete("/{schedule_id}")
async def delete_schedule(
    schedule_id: str,
    current_user: dict = Depends(get_current_user),
):
    success = await svc.delete_schedule(
        schedule_id, current_user.get("tenant_id", ""), current_user.get("role", "")
    )
    if not success:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return {"message": "Schedule deleted"}


@router.post("/{schedule_id}/run-now")
async def run_now(schedule_id: str, current_user: dict = Depends(get_current_user)):
    try:
        result = await svc.run_report_now(
            schedule_id, current_user.get("tenant_id", ""), current_user.get("role", "")
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
