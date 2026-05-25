"""Container image vulnerability scanning endpoints."""
from __future__ import annotations
import time
from fastapi import APIRouter, HTTPException, Depends
from auth_utils import get_current_user
from rbac_utils import require_permission

router = APIRouter(prefix="/api/container-scan", tags=["Container Scan"])

_CONTAINER_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}


async def _db():
    from database import get_database
    return get_database()


def _tenant_filter(current_user) -> dict:
    role = current_user.get("role", "") if isinstance(current_user, dict) else getattr(current_user, "role", "")
    if role in _CONTAINER_SUPER_ROLES:
        return {}
    tid = (current_user.get("tenantId") or current_user.get("tenant_id")) if isinstance(current_user, dict) else (getattr(current_user, "tenantId", None) or getattr(current_user, "tenant_id", None))
    return {"tenantId": tid} if tid else {}


@router.get("/images")
async def list_images(db=Depends(_db), current_user=Depends(require_permission("view:containers"))):
    filt = {**_tenant_filter(current_user), **{"_id": 0}}
    cursor = db["container_images"].find(_tenant_filter(current_user), {"_id": 0}).sort("scanned_at", -1).limit(100)
    return await cursor.to_list(length=100)


@router.post("/images/scan")
async def scan_image(payload: dict, db=Depends(_db), current_user=Depends(require_permission("manage:containers"))):
    tid = (current_user.get("tenantId") or current_user.get("tenant_id")) if isinstance(current_user, dict) else (getattr(current_user, "tenantId", None) or getattr(current_user, "tenant_id", None))
    scan = {
        "id": f"img-{int(time.time())}",
        "image": payload.get("image"),
        "tag": payload.get("tag", "latest"),
        "registry": payload.get("registry", "docker.io"),
        "status": "queued",
        "scanned_at": time.time(),
        "tenantId": tid,
        "triggered_by": current_user.get("sub") if isinstance(current_user, dict) else getattr(current_user, "username", None),
        "vulnerabilities": [],
    }
    await db["container_images"].insert_one(scan)
    scan.pop("_id", None)
    return scan


@router.get("/images/{image_id}")
async def get_image_scan(image_id: str, db=Depends(_db), current_user=Depends(require_permission("view:containers"))):
    query = {"id": image_id, **_tenant_filter(current_user)}
    doc = await db["container_images"].find_one(query, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Image scan not found")
    return doc


@router.get("/vulnerabilities")
async def list_vulnerabilities(db=Depends(_db), current_user=Depends(require_permission("view:containers"))):
    cursor = db["container_vulns"].find(_tenant_filter(current_user), {"_id": 0}).sort("severity_score", -1).limit(200)
    return await cursor.to_list(length=200)


@router.get("/registries")
async def list_registries(db=Depends(_db), current_user=Depends(require_permission("view:containers"))):
    cursor = db["container_registries"].find(_tenant_filter(current_user), {"_id": 0})
    return await cursor.to_list(length=50)


@router.get("/stats")
async def stats(db=Depends(_db), current_user=Depends(require_permission("view:containers"))):
    filt = _tenant_filter(current_user)
    total = await db["container_images"].count_documents(filt)
    vuln_filt = {**filt}
    critical = await db["container_vulns"].count_documents({**vuln_filt, "severity": "CRITICAL"})
    high = await db["container_vulns"].count_documents({**vuln_filt, "severity": "HIGH"})
    medium = await db["container_vulns"].count_documents({**vuln_filt, "severity": "MEDIUM"})
    images_with_critical = await db["container_images"].count_documents({**filt, "critical": {"$gt": 0}})
    return {
        "images_scanned": total,
        "critical_cves": critical,
        "high_cves": high,
        "medium_cves": medium,
        "images_with_critical": images_with_critical,
    }


