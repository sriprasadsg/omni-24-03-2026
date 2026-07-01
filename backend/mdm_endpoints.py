"""Mobile Device Management REST endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from typing import Any, Dict, Optional
import logging

from auth_utils import get_current_user
from auth_types import TokenData
import mdm_service as svc

router = APIRouter(prefix="/api/mdm", tags=["Mobile Device Management"])
logger = logging.getLogger(__name__)


def _tenant(user: TokenData) -> str:
    if not user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return user.tenant_id


@router.get("/summary")
async def get_summary(current_user: TokenData = Depends(get_current_user)):
    return await svc.get_summary(_tenant(current_user))


@router.get("/enrollment-url/{platform}")
async def get_enrollment_url(platform: str, current_user: TokenData = Depends(get_current_user)):
    try:
        return await svc.generate_enrollment_url(_tenant(current_user), platform)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── Devices ───────────────────────────────────────────────────────────────────

@router.get("/devices")
async def list_devices(
    platform: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    current_user: TokenData = Depends(get_current_user),
):
    devices = await svc.list_devices(_tenant(current_user), platform=platform, status=status, limit=limit)
    return {"devices": devices, "total": len(devices)}


@router.post("/devices")
async def enroll_device(
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    try:
        device = await svc.enroll_device(_tenant(current_user), payload)
        return {"device": device, "message": "Device enrolled successfully"}
    except ValueError as exc:
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


@router.post("/devices/{device_id}/unenroll")
async def unenroll_device(device_id: str, current_user: TokenData = Depends(get_current_user)):
    success = await svc.unenroll_device(device_id, _tenant(current_user))
    if not success:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"message": "Device unenrolled"}


@router.post("/devices/{device_id}/action")
async def remote_action(
    device_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    action = payload.get("action", "")
    try:
        result = await svc.remote_action(device_id, _tenant(current_user), action, actor=current_user.username or "")
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── Policies ──────────────────────────────────────────────────────────────────

@router.get("/policies")
async def list_policies(current_user: TokenData = Depends(get_current_user)):
    policies = await svc.list_policies(_tenant(current_user))
    return {"policies": policies, "total": len(policies)}


@router.post("/policies")
async def create_policy(
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    try:
        payload["created_by"] = current_user.username or ""
        policy = await svc.create_policy(_tenant(current_user), payload)
        return {"policy": policy, "message": "MDM policy created"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/policies/{policy_id}")
async def get_policy(policy_id: str, current_user: TokenData = Depends(get_current_user)):
    policy = await svc.get_policy(policy_id, _tenant(current_user))
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return {"policy": policy}


@router.delete("/policies/{policy_id}")
async def delete_policy(policy_id: str, current_user: TokenData = Depends(get_current_user)):
    deleted = await svc.delete_policy(policy_id, _tenant(current_user))
    if not deleted:
        raise HTTPException(status_code=404, detail="Policy not found")
    return {"message": "Policy deleted"}
