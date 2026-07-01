"""Branch Site / Remote Office REST endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Body
from typing import Any, Dict, List
import logging

from auth_utils import get_current_user
from auth_types import TokenData
import branch_site_service as svc

router = APIRouter(prefix="/api/branch-sites", tags=["Branch Sites"])
logger = logging.getLogger(__name__)


def _tenant(user: TokenData) -> str:
    if not user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return user.tenant_id


@router.get("/summary")
async def get_summary(current_user: TokenData = Depends(get_current_user)):
    return await svc.get_summary(_tenant(current_user))


@router.get("")
async def list_sites(current_user: TokenData = Depends(get_current_user)):
    sites = await svc.list_sites_with_stats(_tenant(current_user))
    return {"sites": sites, "total": len(sites)}


@router.post("")
async def create_site(
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    try:
        site = await svc.create_site(_tenant(current_user), payload)
        return {"site": site, "message": "Site created"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{site_id}")
async def get_site(site_id: str, current_user: TokenData = Depends(get_current_user)):
    site = await svc.get_site(site_id, _tenant(current_user))
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    stats = await svc.get_site_stats(site_id, _tenant(current_user))
    return {"site": {**site, **stats}}


@router.patch("/{site_id}")
async def update_site(
    site_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    try:
        site = await svc.update_site(site_id, _tenant(current_user), payload)
        if not site:
            raise HTTPException(status_code=404, detail="Site not found")
        return {"site": site}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/{site_id}")
async def delete_site(site_id: str, current_user: TokenData = Depends(get_current_user)):
    try:
        deleted = await svc.delete_site(site_id, _tenant(current_user))
        if not deleted:
            raise HTTPException(status_code=404, detail="Site not found")
        return {"message": "Site deleted"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{site_id}/assign-agents")
async def assign_agents(
    site_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user: TokenData = Depends(get_current_user),
):
    agent_ids: List[str] = payload.get("agent_ids", [])
    if not agent_ids:
        raise HTTPException(status_code=400, detail="agent_ids list is required")
    try:
        result = await svc.assign_agents(site_id, agent_ids, _tenant(current_user))
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
