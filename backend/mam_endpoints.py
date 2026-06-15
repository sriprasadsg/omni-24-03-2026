"""
Mobile Application Management (MAM) API endpoints.
Routes: /api/mam/
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Any, Dict

from authentication_service import get_current_user
import mam_service as svc

router = APIRouter(prefix="/api/mam", tags=["MAM"])


# ── App Protection Policies ───────────────────────────────────────────────────

def _tenant(current_user) -> str:
    return getattr(current_user, "tenant_id", None) or ""


@router.get("/protection-policies")
async def list_protection_policies(current_user=Depends(get_current_user)) -> Any:
    return await svc.list_protection_policies(_tenant(current_user))


@router.post("/protection-policies")
async def create_protection_policy(body: Dict[str, Any], current_user=Depends(get_current_user)) -> Any:
    try:
        return await svc.create_protection_policy(_tenant(current_user), body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/protection-policies/{policy_id}")
async def get_protection_policy(policy_id: str, current_user=Depends(get_current_user)) -> Any:
    item = await svc.get_protection_policy(_tenant(current_user), policy_id)
    if not item:
        raise HTTPException(status_code=404, detail="Policy not found")
    return item


@router.put("/protection-policies/{policy_id}")
async def update_protection_policy(policy_id: str, body: Dict[str, Any], current_user=Depends(get_current_user)) -> Any:
    try:
        return await svc.update_protection_policy(_tenant(current_user), policy_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/protection-policies/{policy_id}")
async def delete_protection_policy(policy_id: str, current_user=Depends(get_current_user)) -> Any:
    await svc.delete_protection_policy(_tenant(current_user), policy_id)
    return {"deleted": policy_id}


@router.post("/protection-policies/{policy_id}/assign")
async def assign_protection_policy(policy_id: str, body: Dict[str, Any], current_user=Depends(get_current_user)) -> Any:
    try:
        return await svc.update_protection_policy(_tenant(current_user), policy_id, {
            "assigned_groups": body.get("groups", []),
            "assigned_apps": body.get("apps", []),
        })
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ── App Configuration Policies ────────────────────────────────────────────────

@router.get("/config-policies")
async def list_config_policies(current_user=Depends(get_current_user)) -> Any:
    return await svc.list_config_policies(_tenant(current_user))


@router.post("/config-policies")
async def create_config_policy(body: Dict[str, Any], current_user=Depends(get_current_user)) -> Any:
    try:
        return await svc.create_config_policy(_tenant(current_user), body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/config-policies/{policy_id}")
async def get_config_policy(policy_id: str, current_user=Depends(get_current_user)) -> Any:
    item = await svc.get_config_policy(_tenant(current_user), policy_id)
    if not item:
        raise HTTPException(status_code=404, detail="Config policy not found")
    return item


@router.put("/config-policies/{policy_id}")
async def update_config_policy(policy_id: str, body: Dict[str, Any], current_user=Depends(get_current_user)) -> Any:
    try:
        return await svc.update_config_policy(_tenant(current_user), policy_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/config-policies/{policy_id}")
async def delete_config_policy(policy_id: str, current_user=Depends(get_current_user)) -> Any:
    await svc.delete_config_policy(_tenant(current_user), policy_id)
    return {"deleted": policy_id}


# ── Managed Apps ──────────────────────────────────────────────────────────────

@router.get("/managed-apps")
async def list_managed_apps(current_user=Depends(get_current_user)) -> Any:
    return await svc.list_managed_apps(_tenant(current_user))


@router.post("/managed-apps/{app_id}/wipe-data")
async def wipe_app_data(app_id: str, current_user=Depends(get_current_user)) -> Any:
    return await svc.selective_wipe(_tenant(current_user), app_id)
