"""Mobile Device Management REST endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from rbac_utils import require_permission
from typing import Any, Dict, Optional
import logging

from auth_utils import get_current_user
from auth_types import TokenData
import android_mdm_service
import fleet_service
import intune_service
import mdm_service as svc
from database import get_database

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
    current_user: TokenData = Depends(require_permission("manage:assets")),
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
    current_user: TokenData = Depends(require_permission("manage:assets")),
):
    try:
        device = await svc.update_device(device_id, _tenant(current_user), payload)
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        return {"device": device}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/devices/{device_id}/unenroll")
async def unenroll_device(device_id: str, current_user: TokenData = Depends(require_permission("manage:assets"))):
    success = await svc.unenroll_device(device_id, _tenant(current_user))
    if not success:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"message": "Device unenrolled"}


@router.post("/devices/{device_id}/action")
async def remote_action(
    device_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(require_permission("manage:assets")),
):
    action = payload.get("action", "")
    tenant = _tenant(current_user)
    device = await svc.get_device(device_id, tenant)
    if device and device.get("source") == "intune":
        # Wave 5: an Intune device's action is sent to Microsoft Graph for real, not queued.
        if device.get("intuneRemoved") or device.get("intuneDisconnected"):
            raise HTTPException(status_code=409, detail="This device is no longer in the connected Intune")
        return await _intune(intune_service.action(get_database(), tenant, device, str(action), current_user.username or "",
                                                   payload.get("confirm")))
    if device and device.get("source") == "android":
        if device.get("androidRemoved") or device.get("androidDisconnected"):
            raise HTTPException(status_code=409, detail="This device is no longer in the connected Android Enterprise")
        return await _android(android_mdm_service.action(get_database(), tenant, device, str(action),
                                                         current_user.username or "", payload.get("confirm")))
    if device and device.get("source") == "fleet":
        if device.get("fleetRemoved") or device.get("fleetDisconnected"):
            raise HTTPException(status_code=409, detail="This device is no longer in the connected Fleet")
        return await _fleet(fleet_service.action(get_database(), tenant, device, str(action), current_user.username or ""))
    try:
        result = await svc.remote_action(device_id, tenant, action, actor=current_user.username or "")
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── Intune connector (Wave 5) ────────────────────────────────────────────────

async def _intune(coro):
    try:
        return await coro
    except intune_service.IntuneError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))


@router.get("/intune")
async def get_intune(current_user: TokenData = Depends(get_current_user)):
    """Whether this organization's Intune is connected, its ids, last sync and error; never the secret."""
    return await intune_service.get_config(get_database(), _tenant(current_user))


@router.put("/intune")
async def put_intune(payload: Dict[str, Any] = Body(...), current_user: TokenData = Depends(require_permission("manage:assets"))):
    """Connect or update Intune: azureTenantId, clientId and clientSecret (the secret may be left out to keep it)."""
    return await _intune(intune_service.save_config(get_database(), _tenant(current_user), str(payload.get("azureTenantId") or ""),
                                                    str(payload.get("clientId") or ""), payload.get("clientSecret") or None,
                                                    current_user.username or ""))


@router.delete("/intune")
async def delete_intune(current_user: TokenData = Depends(require_permission("manage:assets"))):
    await _intune(intune_service.disconnect(get_database(), _tenant(current_user), current_user.username or ""))
    return {"success": True}


@router.post("/intune/sync")
async def sync_intune(current_user: TokenData = Depends(require_permission("manage:assets"))):
    """Read Intune's managed devices now (also done every hour)."""
    return await _intune(intune_service.sync(get_database(), _tenant(current_user), current_user.username or ""))


# ── Android Enterprise connector (Android Management API) ───────────────────────

async def _android(coro):
    try:
        return await coro
    except android_mdm_service.AndroidError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))


@router.get("/android")
async def get_android(current_user: TokenData = Depends(get_current_user)):
    """Whether this organization's Android Enterprise is connected, its project, enterprise and last sync; never the key."""
    return await android_mdm_service.get_config(get_database(), _tenant(current_user))


@router.put("/android")
async def put_android(payload: Dict[str, Any] = Body(...), current_user: TokenData = Depends(require_permission("manage:assets"))):
    """Connect or update: serviceAccountKey (the JSON, may be left out to keep it) and enterprise (enterprises/...)."""
    return await _android(android_mdm_service.save_config(get_database(), _tenant(current_user),
                                                          payload.get("serviceAccountKey") or None,
                                                          payload.get("enterprise") or None, current_user.username or ""))


@router.delete("/android")
async def delete_android(current_user: TokenData = Depends(require_permission("manage:assets"))):
    await _android(android_mdm_service.disconnect(get_database(), _tenant(current_user), current_user.username or ""))
    return {"success": True}


@router.post("/android/signup")
async def android_signup(payload: Dict[str, Any] = Body(...), current_user: TokenData = Depends(require_permission("manage:assets"))):
    """A Google sign-up link that creates the Android Enterprise and returns to callbackUrl with an enterprise token."""
    return await _android(android_mdm_service.signup_url(get_database(), _tenant(current_user),
                                                         str(payload.get("callbackUrl") or ""), current_user.username or ""))


@router.post("/android/enterprise")
async def android_enterprise(payload: Dict[str, Any] = Body(...), current_user: TokenData = Depends(require_permission("manage:assets"))):
    """Finish the sign-up with the enterpriseToken Google returned."""
    return await _android(android_mdm_service.complete_signup(get_database(), _tenant(current_user),
                                                              str(payload.get("enterpriseToken") or ""),
                                                              str(payload.get("displayName") or ""), current_user.username or ""))


@router.post("/android/enrollment-token")
async def android_enrollment_token(current_user: TokenData = Depends(require_permission("manage:assets"))):
    """A 24-hour enrollment QR code and work-profile link."""
    return await _android(android_mdm_service.enrollment_token(get_database(), _tenant(current_user), current_user.username or ""))


@router.post("/android/sync")
async def sync_android(current_user: TokenData = Depends(require_permission("manage:assets"))):
    """Read the enterprise's devices now (also done every hour)."""
    return await _android(android_mdm_service.sync(get_database(), _tenant(current_user), current_user.username or ""))


# ── Fleet connector (open source, osquery) ─────────────────────────────────────

async def _fleet(coro):
    try:
        return await coro
    except fleet_service.FleetError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))


@router.get("/fleet")
async def get_fleet(current_user: TokenData = Depends(get_current_user)):
    """Whether this organization's Fleet is connected, its address, last sync and error; never the token."""
    return await fleet_service.get_config(get_database(), _tenant(current_user))


@router.put("/fleet")
async def put_fleet(payload: Dict[str, Any] = Body(...), current_user: TokenData = Depends(require_permission("manage:assets"))):
    """Connect or update Fleet: baseUrl and apiToken (the token may be left out to keep it)."""
    return await _fleet(fleet_service.save_config(get_database(), _tenant(current_user), str(payload.get("baseUrl") or ""),
                                                  payload.get("apiToken") or None, current_user.username or ""))


@router.delete("/fleet")
async def delete_fleet(current_user: TokenData = Depends(require_permission("manage:assets"))):
    await _fleet(fleet_service.disconnect(get_database(), _tenant(current_user), current_user.username or ""))
    return {"success": True}


@router.post("/fleet/sync")
async def sync_fleet(current_user: TokenData = Depends(require_permission("manage:assets"))):
    """Read Fleet's hosts now (also done every hour)."""
    return await _fleet(fleet_service.sync(get_database(), _tenant(current_user), current_user.username or ""))


# ── Policies ──────────────────────────────────────────────────────────────────

@router.get("/policies")
async def list_policies(current_user: TokenData = Depends(get_current_user)):
    policies = await svc.list_policies(_tenant(current_user))
    return {"policies": policies, "total": len(policies)}


@router.post("/policies")
async def create_policy(
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(require_permission("manage:assets")),
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
async def delete_policy(policy_id: str, current_user: TokenData = Depends(require_permission("manage:assets"))):
    deleted = await svc.delete_policy(policy_id, _tenant(current_user))
    if not deleted:
        raise HTTPException(status_code=404, detail="Policy not found")
    return {"message": "Policy deleted"}
