"""IaC Scanner API — scan code/repo, results, config."""
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from database import get_database
from auth_types import TokenData
from tenant_context import get_tenant_id
from rbac_service import rbac_service
import iac_scanner_service as svc
import logging

router = APIRouter(prefix="/api/iac", tags=["IaC Scanner"])
logger = logging.getLogger(__name__)


@router.post("/scan")
async def scan_code(
    code: str = Body(..., embed=True),
    filename: str = Body("main.tf", embed=True),
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
):
    if len(code) > 500000:
        raise HTTPException(status_code=413, detail="Code too large (max 500KB)")
    result = svc.scan_code(code, filename)
    db = get_database()
    await svc.save_result(db, get_tenant_id(), result)
    return result


@router.get("/results")
async def list_results(current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard"))):
    db = get_database()
    items = await svc.list_results(db, get_tenant_id())
    return {"items": items, "count": len(items)}


@router.get("/scan-config")
async def get_config(current_user: TokenData = Depends(rbac_service.has_permission("manage:settings"))):
    db = get_database()
    config = await svc.get_config(db, get_tenant_id())
    return {"config": config}


@router.post("/scan-config")
async def set_config(payload: dict = Body(...), current_user: TokenData = Depends(rbac_service.has_permission("manage:settings"))):
    db = get_database()
    config = await svc.set_config(db, get_tenant_id(), payload)
    return {"config": config}
