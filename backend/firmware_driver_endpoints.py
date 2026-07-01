"""
Firmware and Driver Update Management API endpoints.
Routes: /api/firmware-drivers/
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Any, Dict, Optional

from authentication_service import get_current_user
import firmware_driver_service as svc

router = APIRouter(prefix="/api/firmware-drivers", tags=["Firmware & Drivers"])


@router.get("/inventory")
async def get_inventory(current_user=Depends(get_current_user)) -> Any:
    tenant_id = getattr(current_user, "tenant_id", "") or ""
    return await svc.get_inventory(tenant_id)


@router.get("/inventory/{asset_id}")
async def get_asset_inventory(asset_id: str, current_user=Depends(get_current_user)) -> Any:
    tenant_id = getattr(current_user, "tenant_id", "") or ""
    return await svc.get_asset_inventory(tenant_id, asset_id)


@router.get("/updates/available")
async def get_available_updates(
    update_type: Optional[str] = None,
    current_user=Depends(get_current_user),
) -> Any:
    tenant_id = getattr(current_user, "tenant_id", "") or ""
    return await svc.get_available_updates(tenant_id, update_type)


@router.post("/updates/deploy")
async def deploy_updates(body: Dict[str, Any], current_user=Depends(get_current_user)) -> Any:
    tenant_id = getattr(current_user, "tenant_id", "") or ""
    try:
        return await svc.create_deployment_job(tenant_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/updates/jobs")
async def list_deployment_jobs(current_user=Depends(get_current_user)) -> Any:
    tenant_id = getattr(current_user, "tenant_id", "") or ""
    return await svc.list_deployment_jobs(tenant_id)


@router.get("/reports/compliance")
async def compliance_report(current_user=Depends(get_current_user)) -> Any:
    tenant_id = getattr(current_user, "tenant_id", "") or ""
    return await svc.get_compliance_report(tenant_id)

