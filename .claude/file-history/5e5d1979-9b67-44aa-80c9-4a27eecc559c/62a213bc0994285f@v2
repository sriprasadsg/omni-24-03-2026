"""Domain Scanner API — ad-hoc scan + scheduled domain management."""
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from typing import Optional
from database import get_database
from auth_types import TokenData
from tenant_context import get_tenant_id
from rbac_service import rbac_service
import domain_scanner_service as svc
import logging

router = APIRouter(prefix="/api/domain-scanner", tags=["Domain Scanner"])
logger = logging.getLogger(__name__)


@router.get("/scan")
async def scan_domain(domain: str = Query(..., min_length=1, max_length=253), current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard"))):
    db = get_database()
    result = await svc.scan_domain(db, get_tenant_id(), domain)
    return result


@router.post("/scheduled")
async def schedule_domain(payload: dict = Body(...), current_user: TokenData = Depends(rbac_service.has_permission("manage:settings"))):
    domain = payload.get("domain", "")
    if not domain:
        raise HTTPException(status_code=400, detail="domain required")
    db = get_database()
    doc = await svc.schedule_domain(db, get_tenant_id(), domain)
    return {"scheduled": doc}


@router.get("/scheduled")
async def list_scheduled(current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard"))):
    db = get_database()
    items = await svc.list_scheduled(db, get_tenant_id())
    return {"items": items, "count": len(items)}
