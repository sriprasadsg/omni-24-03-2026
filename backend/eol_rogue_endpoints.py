"""
End-of-Life Asset Detection and Rogue Asset Detection API endpoints.
Routes: /api/asset-intelligence/
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Any, Dict

from authentication_service import get_current_user
import eol_rogue_service as svc

router = APIRouter(prefix="/api/asset-intelligence", tags=["Asset Intelligence"])


@router.get("/eol")
async def list_eol_assets(current_user=Depends(get_current_user)) -> Any:
    tenant_id = getattr(current_user, "tenant_id", "") or ""
    return await svc.get_eol_assets(tenant_id)


@router.get("/eol/summary")
async def eol_summary(current_user=Depends(get_current_user)) -> Any:
    tenant_id = getattr(current_user, "tenant_id", "") or ""
    return await svc.get_eol_summary(tenant_id)


@router.get("/rogue")
async def list_rogue_assets(current_user=Depends(get_current_user)) -> Any:
    tenant_id = getattr(current_user, "tenant_id", "") or ""
    return await svc.get_rogue_assets(tenant_id)


@router.get("/rogue/summary")
async def rogue_summary(current_user=Depends(get_current_user)) -> Any:
    tenant_id = getattr(current_user, "tenant_id", "") or ""
    return await svc.get_rogue_summary(tenant_id)


@router.post("/rogue/{asset_id}/authorize")
async def authorize_asset(asset_id: str, current_user=Depends(get_current_user)) -> Any:
    tenant_id = getattr(current_user, "tenant_id", "") or ""
    try:
        return await svc.authorize_asset(tenant_id, asset_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

