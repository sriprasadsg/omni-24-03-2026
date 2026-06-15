"""Third-Party Application Catalog REST endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from typing import Any, Dict, Optional
import logging

from auth_utils import get_current_user
from auth_types import TokenData
import app_catalog_service as svc

router = APIRouter(prefix="/api/app-catalog", tags=["App Catalog"])
logger = logging.getLogger(__name__)


def _tenant(user: TokenData) -> str:
    if not user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return user.tenant_id


@router.get("/summary")
async def get_summary(current_user: TokenData = Depends(get_current_user)):
    return await svc.get_summary(_tenant(current_user))


@router.get("/categories")
async def get_categories(current_user: TokenData = Depends(get_current_user)):
    cats = await svc.get_categories(_tenant(current_user))
    return {"categories": cats}


@router.get("/apps")
async def list_apps(
    category: Optional[str] = Query(None),
    platform: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(200, le=500),
    current_user: TokenData = Depends(get_current_user),
):
    apps = await svc.list_apps(_tenant(current_user), category=category, platform=platform, search=search, limit=limit)
    return {"apps": apps, "total": len(apps)}


@router.post("/apps")
async def add_custom_app(
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    try:
        payload["created_by"] = current_user.username or ""
        app = await svc.add_custom_app(_tenant(current_user), payload)
        return {"app": app, "message": "Custom app added to catalog"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/apps/{app_id}")
async def delete_custom_app(app_id: str, current_user: TokenData = Depends(get_current_user)):
    deleted = await svc.delete_custom_app(app_id, _tenant(current_user))
    if not deleted:
        raise HTTPException(status_code=404, detail="App not found or is a built-in app")
    return {"message": "Custom app removed"}
