"""
Android Enterprise & Samsung Knox API endpoints.
Routes: /api/android-enterprise/
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Any, Dict

from authentication_service import get_current_user
import android_enterprise_service as svc

router = APIRouter(prefix="/api/android-enterprise", tags=["Android Enterprise"])


# â”€â”€ Enrollment Profiles â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/profiles")
async def list_profiles(current_user=Depends(get_current_user)) -> Any:
    tenant_id = getattr(current_user, "tenant_id", "") or ""
    return await svc.list_profiles(tenant_id)


@router.post("/profiles")
async def create_profile(body: Dict[str, Any], current_user=Depends(get_current_user)) -> Any:
    tenant_id = getattr(current_user, "tenant_id", "") or ""
    try:
        return await svc.create_profile(tenant_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/profiles/{profile_id}")
async def get_profile(profile_id: str, current_user=Depends(get_current_user)) -> Any:
    tenant_id = getattr(current_user, "tenant_id", "") or ""
    item = await svc.get_profile(tenant_id, profile_id)
    if not item:
        raise HTTPException(status_code=404, detail="Profile not found")
    return item


@router.put("/profiles/{profile_id}")
async def update_profile(profile_id: str, body: Dict[str, Any], current_user=Depends(get_current_user)) -> Any:
    tenant_id = getattr(current_user, "tenant_id", "") or ""
    try:
        return await svc.update_profile(tenant_id, profile_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: str, current_user=Depends(get_current_user)) -> Any:
    tenant_id = getattr(current_user, "tenant_id", "") or ""
    await svc.delete_profile(tenant_id, profile_id)
    return {"deleted": profile_id}


@router.get("/profiles/{profile_id}/enrollment-url")
async def get_enrollment_url(profile_id: str, current_user=Depends(get_current_user)) -> Any:
    tenant_id = getattr(current_user, "tenant_id", "") or ""
    try:
        return await svc.get_enrollment_url(tenant_id, profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# â”€â”€ Samsung Knox â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.post("/knox/license")
async def set_knox_license(body: Dict[str, Any], current_user=Depends(get_current_user)) -> Any:
    tenant_id = getattr(current_user, "tenant_id", "") or ""
    try:
        return await svc.set_knox_license(tenant_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/knox/status")
async def get_knox_status(current_user=Depends(get_current_user)) -> Any:
    tenant_id = getattr(current_user, "tenant_id", "") or ""
    return await svc.get_knox_status(tenant_id)


# â”€â”€ Dedicated Devices (Kiosk) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.post("/dedicated-device/configure")
async def configure_dedicated_device(body: Dict[str, Any], current_user=Depends(get_current_user)) -> Any:
    tenant_id = getattr(current_user, "tenant_id", "") or ""
    try:
        return await svc.configure_dedicated_device(tenant_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/dedicated-device/configs")
async def list_dedicated_device_configs(current_user=Depends(get_current_user)) -> Any:
    tenant_id = getattr(current_user, "tenant_id", "") or ""
    return await svc.list_dedicated_device_configs(tenant_id)

