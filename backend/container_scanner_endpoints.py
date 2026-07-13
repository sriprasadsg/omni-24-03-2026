"""Container Scanner API — scan image, list results."""
import re
import uuid
from datetime import datetime, timezone
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

_CDX_SEV_MAP = {"CRITICAL": "critical", "HIGH": "high", "MEDIUM": "medium", "LOW": "low", "UNKNOWN": "unknown"}

def _to_cyclonedx(scan_result: dict) -> dict:
    components, comp_ref = [], {}
    for v in scan_result.get("vulns", []):
        key = (v["pkg_name"], v["installed_version"])
        if key not in comp_ref:
            ref = f"pkg:{v['pkg_name']}@{v['installed_version']}"
            comp_ref[key] = ref
            components.append({
                "type": "library",
                "bom-ref": ref,
                "name": v["pkg_name"],
                "version": v["installed_version"],
                "purl": f"pkg:generic/{v['pkg_name']}@{v['installed_version']}",
            })
    vulnerabilities = [{
        "id": v["id"],
        "source": {"name": "NVD"},
        "ratings": [{"severity": _CDX_SEV_MAP.get(v["severity"], "unknown")}],
        "description": v.get("description", ""),
        "affects": [{"ref": comp_ref[(v["pkg_name"], v["installed_version"])]}],
    } for v in scan_result.get("vulns", [])]

    cdx = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "metadata": {"component": {"type": "container", "name": scan_result.get("image", "")}},
        "components": components,
        "vulnerabilities": vulnerabilities,
    }
    if scan_result.get("simulated"):
        cdx["metadata"]["properties"] = [{"name": "omniagent:simulated", "value": "true"}]
    return cdx

@router.get("/results/{scan_id}/sbom")
async def container_result_sbom(scan_id: str, current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard"))):
    db = get_database()
    tenant_id = get_tenant_id()
    result = await db._db.container_scan_results.find_one({"scan_id": scan_id, "tenantId": tenant_id}, {"_id": 0})
    if not result:
        raise HTTPException(status_code=404, detail="Scan result not found")
    return _to_cyclonedx(result)

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
