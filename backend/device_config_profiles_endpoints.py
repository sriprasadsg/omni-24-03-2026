"""
Device Configuration Profiles API endpoints.
Routes: /api/device-config-profiles/
Covers: Browser, USB, Wi-Fi, VPN, Kiosk profile types.
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Any, Dict, Optional

from authentication_service import get_current_user
import device_config_profiles_service as svc

router = APIRouter(prefix="/api/device-config-profiles", tags=["Device Config Profiles"])


@router.get("/types")
async def get_profile_types(current_user=Depends(get_current_user)) -> Any:
    return await svc.get_profile_types()


@router.get("")
async def list_profiles(
    profile_type: Optional[str] = None,
    current_user=Depends(get_current_user),
) -> Any:
    tenant_id = getattr(current_user, "tenant_id", "") or ""
    return await svc.list_profiles(tenant_id, profile_type)


@router.post("")
async def create_profile(body: Dict[str, Any], current_user=Depends(get_current_user)) -> Any:
    tenant_id = getattr(current_user, "tenant_id", "") or ""
    try:
        return await svc.create_profile(tenant_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{profile_id}")
async def get_profile(profile_id: str, current_user=Depends(get_current_user)) -> Any:
    tenant_id = getattr(current_user, "tenant_id", "") or ""
    item = await svc.get_profile(tenant_id, profile_id)
    if not item:
        raise HTTPException(status_code=404, detail="Profile not found")
    return item


@router.put("/{profile_id}")
async def update_profile(profile_id: str, body: Dict[str, Any], current_user=Depends(get_current_user)) -> Any:
    tenant_id = getattr(current_user, "tenant_id", "") or ""
    try:
        return await svc.update_profile(tenant_id, profile_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/{profile_id}")
async def delete_profile(profile_id: str, current_user=Depends(get_current_user)) -> Any:
    tenant_id = getattr(current_user, "tenant_id", "") or ""
    await svc.delete_profile(tenant_id, profile_id)
    return {"deleted": profile_id}


@router.post("/{profile_id}/assign")
async def assign_profile(profile_id: str, body: Dict[str, Any], current_user=Depends(get_current_user)) -> Any:
    tenant_id = getattr(current_user, "tenant_id", "") or ""
    try:
        return await svc.assign_profile(tenant_id, profile_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{profile_id}/assignments")
async def get_assignments(profile_id: str, current_user=Depends(get_current_user)) -> Any:
    tenant_id = getattr(current_user, "tenant_id", "") or ""
    item = await svc.get_profile(tenant_id, profile_id)
    if not item:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {
        "profile_id": profile_id,
        "assigned_groups": item.get("assigned_groups", []),
        "assigned_devices": item.get("assigned_devices", []),
    }

