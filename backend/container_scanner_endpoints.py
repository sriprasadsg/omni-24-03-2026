"""Container Scanner API — scan image, list results."""
import re
from fastapi import APIRouter, Depends, HTTPException, Body, Request, Response
from database import get_database
from auth_types import TokenData
from tenant_context import get_tenant_id
from rbac_service import rbac_service
from rate_limiter import limiter
import container_scanner_service as svc
import logging

router = APIRouter(prefix="/api/container", tags=["Container Scanner"])
logger = logging.getLogger(__name__)

# [registry[:port]/](namespace/)*name(:tag|@sha256:digest) — conservative allow-list for image references
_IMAGE_NAME_RE = re.compile(
    r'^(?:[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?(?::[0-9]+)?/)?'
    r'[a-zA-Z0-9]+(?:[._-][a-zA-Z0-9]+)*(?:/[a-zA-Z0-9]+(?:[._-][a-zA-Z0-9]+)*)*'
    r'(?::[a-zA-Z0-9_.-]+|@sha256:[a-f0-9]{64})$'
)


@router.post("/scan")
@limiter.limit("10/minute")
async def scan_image(
    request: Request,
    response: Response,
    image_name: str = Body(..., embed=True),
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
):
    if not image_name:
        image_name = "nginx:latest"
    elif ":" not in image_name:
        image_name = f"{image_name}:latest"
    if not _IMAGE_NAME_RE.match(image_name) or len(image_name) > 256:
        raise HTTPException(status_code=422, detail="Invalid image_name format")
    result = svc.scan_image(image_name)
    db = get_database()
    await svc.save_result(db, get_tenant_id(), result)
    return result


@router.get("/results")
async def list_results(current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard"))):
    db = get_database()
    items = await svc.list_results(db, get_tenant_id())
    return {"items": items, "count": len(items)}
