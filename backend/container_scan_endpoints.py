"""Container image vulnerability scanning endpoints."""
from __future__ import annotations
import time
from fastapi import APIRouter, HTTPException, Depends
from auth_utils import get_current_user

router = APIRouter(prefix="/api/container-scan", tags=["Container Scan"])


async def _db():
    from database import get_database
    return get_database()


@router.get("/images")
async def list_images(db=Depends(_db)):
    cursor = db["container_images"].find({}, {"_id": 0}).sort("scanned_at", -1).limit(100)
    items = await cursor.to_list(length=100)
    return items


@router.post("/images/scan")
async def scan_image(payload: dict, db=Depends(_db), current_user=Depends(get_current_user)):
    scan = {
        "id": f"img-{int(time.time())}",
        "image": payload.get("image"),
        "tag": payload.get("tag", "latest"),
        "registry": payload.get("registry", "docker.io"),
        "status": "queued",
        "scanned_at": time.time(),
        "triggered_by": current_user.get("sub"),
        "vulnerabilities": [],
    }
    await db["container_images"].insert_one(scan)
    scan.pop("_id", None)
    return scan


@router.get("/images/{image_id}")
async def get_image_scan(image_id: str, db=Depends(_db)):
    doc = await db["container_images"].find_one({"id": image_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Image scan not found")
    return doc


@router.get("/vulnerabilities")
async def list_vulnerabilities(db=Depends(_db)):
    cursor = db["container_vulns"].find({}, {"_id": 0}).sort("severity_score", -1).limit(200)
    items = await cursor.to_list(length=200)
    return items


@router.get("/registries")
async def list_registries(db=Depends(_db)):
    cursor = db["container_registries"].find({}, {"_id": 0})
    items = await cursor.to_list(length=50)
    return items


@router.get("/stats")
async def stats(db=Depends(_db)):
    total = await db["container_images"].count_documents({})
    critical = await db["container_vulns"].count_documents({"severity": "CRITICAL"})
    high = await db["container_vulns"].count_documents({"severity": "HIGH"})
    medium = await db["container_vulns"].count_documents({"severity": "MEDIUM"})
    images_with_critical = await db["container_images"].count_documents({"critical": {"$gt": 0}})
    return {
        "images_scanned": total,
        "critical_cves": critical,
        "high_cves": high,
        "medium_cves": medium,
        "images_with_critical": images_with_critical,
    }


