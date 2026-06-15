"""Windows Autopilot REST endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Body
from typing import Any, Dict, List, Optional
import logging

from auth_utils import get_current_user
from auth_types import TokenData
import autopilot_service as svc

router = APIRouter(prefix="/api/autopilot", tags=["Windows Autopilot"])
logger = logging.getLogger(__name__)


def _tenant(user: TokenData) -> str:
    if not user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return user.tenant_id


# ── Summary ───────────────────────────────────────────────────────────────────

@router.get("/summary")
async def get_summary(current_user: TokenData = Depends(get_current_user)):
    return await svc.get_summary(_tenant(current_user))


# ── Devices ───────────────────────────────────────────────────────────────────

@router.get("/devices")
async def list_devices(
    status: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    current_user: TokenData = Depends(get_current_user),
):
    devices = await svc.list_devices(_tenant(current_user), status=status, limit=limit)
    return {"devices": devices, "total": len(devices)}


@router.post("/devices")
async def register_device(
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    try:
        device = await svc.register_device(_tenant(current_user), payload)
        return {"device": device, "message": "Device registered successfully"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/devices/import")
async def import_devices_csv(
    file: UploadFile = File(...),
    current_user: TokenData = Depends(get_current_user),
):
    content = await file.read()
    try:
        result = await svc.import_devices_csv(_tenant(current_user), content.decode("utf-8-sig"))
        return result
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/devices/{device_id}")
async def get_device(device_id: str, current_user: TokenData = Depends(get_current_user)):
    device = await svc.get_device(device_id, _tenant(current_user))
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"device": device}


@router.patch("/devices/{device_id}")
async def update_device(
    device_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    try:
        device = await svc.update_device(device_id, _tenant(current_user), payload)
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        return {"device": device}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/devices/{device_id}")
async def delete_device(device_id: str, current_user: TokenData = Depends(get_current_user)):
    deleted = await svc.delete_device(device_id, _tenant(current_user))
    if not deleted:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"message": "Device deregistered"}


# ── Deployment Profiles ───────────────────────────────────────────────────────

@router.get("/profiles")
async def list_profiles(current_user: TokenData = Depends(get_current_user)):
    profiles = await svc.list_profiles(_tenant(current_user))
    return {"profiles": profiles, "total": len(profiles)}


@router.post("/profiles")
async def create_profile(
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    try:
        payload["created_by"] = current_user.username or ""
        profile = await svc.create_profile(_tenant(current_user), payload)
        return {"profile": profile, "message": "Deployment profile created"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/profiles/{profile_id}")
async def get_profile(profile_id: str, current_user: TokenData = Depends(get_current_user)):
    profile = await svc.get_profile(profile_id, _tenant(current_user))
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"profile": profile}


@router.patch("/profiles/{profile_id}")
async def update_profile(
    profile_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    try:
        profile = await svc.update_profile(profile_id, _tenant(current_user), payload)
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        return {"profile": profile}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: str, current_user: TokenData = Depends(get_current_user)):
    try:
        deleted = await svc.delete_profile(profile_id, _tenant(current_user))
        if not deleted:
            raise HTTPException(status_code=404, detail="Profile not found")
        return {"message": "Profile deleted"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/profiles/{profile_id}/assign")
async def assign_profile_to_devices(
    profile_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    device_ids: List[str] = payload.get("device_ids", [])
    if not device_ids or not isinstance(device_ids, list):
        raise HTTPException(status_code=400, detail="device_ids list is required")
    try:
        result = await svc.assign_profile(profile_id, device_ids, _tenant(current_user))
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── ESP (Enrollment Status Page) ─────────────────────────────────────────────

@router.get("/esp/events")
async def list_esp_events(
    limit: int = Query(50, le=200),
    current_user: TokenData = Depends(get_current_user),
):
    events = await svc.list_esp_events(_tenant(current_user), limit=limit)
    return {"events": events, "total": len(events)}


@router.post("/esp/{device_id}")
async def update_esp_status(
    device_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    try:
        device = await svc.update_esp_status(
            device_id,
            _tenant(current_user),
            stage=payload.get("stage", ""),
            progress=int(payload.get("progress", 0)),
            error=payload.get("error"),
        )
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        return {"device": device}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
