"""Container Scanner API — scan image, list results."""
from fastapi import APIRouter, Depends, HTTPException, Body
from database import get_database
from auth_types import TokenData
from tenant_context import get_tenant_id
from rbac_service import rbac_service
import container_scanner_service as svc
import logging

router = APIRouter(prefix="/api/container", tags=["Container Scanner"])
logger = logging.getLogger(__name__)


@router.post("/scan")
async def scan_image(
    image_name: str = Body(..., embed=True),
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
):
    if not image_name or ":" not in image_name and "/" in image_name:
        image_name = f"{image_name}:latest" if image_name else "nginx:latest"
    result = svc.scan_image(image_name)
    db = get_database()
    await svc.save_result(db, get_tenant_id(), result)
    return result


@router.get("/results")
async def list_results(current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard"))):
    db = get_database()
    items = await svc.list_results(db, get_tenant_id())
    return {"items": items, "count": len(items)}
