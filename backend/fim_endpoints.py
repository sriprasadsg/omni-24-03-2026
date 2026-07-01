"""File Integrity Monitoring (FIM) Endpoints — /api/fim/"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from authentication_service import get_current_user, TokenData
from database import get_database
from datetime import datetime, timezone
from typing import Optional, List
import uuid

router = APIRouter(prefix="/api/fim", tags=["FIM"])

# Default critical paths to monitor per platform
DEFAULT_PATHS = {
    "linux": [
        "/etc/", "/bin/", "/usr/bin/", "/usr/sbin/", "/sbin/",
        "/var/www/", "/home/", "/root/", "/boot/", "/lib/",
        "/etc/passwd", "/etc/shadow", "/etc/sudoers", "/etc/crontab",
        "/etc/ssh/sshd_config",
    ],
    "windows": [
        "C:\\Windows\\System32\\",
        "C:\\Windows\\SysWOW64\\",
        "C:\\Program Files\\",
        "C:\\Program Files (x86)\\",
        "HKEY_LOCAL_MACHINE\\SOFTWARE\\",
        "HKEY_LOCAL_MACHINE\\SYSTEM\\CurrentControlSet\\",
        "C:\\Windows\\System32\\drivers\\etc\\hosts",
    ],
    "macos": [
        "/etc/", "/bin/", "/usr/bin/", "/usr/sbin/", "/sbin/",
        "/Library/LaunchDaemons/", "/Library/LaunchAgents/",
        "/private/etc/",
    ],
}

CHANGE_TYPES = {"added", "modified", "deleted", "permissions", "ownership"}


class PathCreate(BaseModel):
    path: str
    platform: str = "linux"
    recursive: bool = True
    check_interval_seconds: int = 300
    alert_on: List[str] = ["added", "modified", "deleted"]
    ignore_patterns: List[str] = []


class PathUpdate(BaseModel):
    recursive: Optional[bool] = None
    check_interval_seconds: Optional[int] = None
    alert_on: Optional[List[str]] = None
    ignore_patterns: Optional[List[str]] = None
    enabled: Optional[bool] = None


def _strip_id(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc


@router.get("/paths")
async def list_monitored_paths(
    platform: Optional[str] = Query(None),
    agent_id: Optional[str] = Query(None),
    current_user: TokenData = Depends(get_current_user),
):
    """List all monitored FIM paths for the tenant."""
    db = get_database()
    query: dict = {"tenantId": current_user.tenant_id}
    if platform:
        query["platform"] = platform
    if agent_id:
        query["agent_id"] = agent_id
    paths = []
    async for doc in db.fim_paths.find(query).sort("created_at", -1):
        _strip_id(doc)
        paths.append(doc)
    return paths


@router.post("/paths", status_code=201)
async def create_monitored_path(
    body: PathCreate,
    current_user: TokenData = Depends(get_current_user),
):
    """Add a path to FIM monitoring."""
    db = get_database()
    if body.platform not in DEFAULT_PATHS:
        raise HTTPException(status_code=400, detail=f"platform must be one of: {list(DEFAULT_PATHS.keys())}")
    invalid = set(body.alert_on) - CHANGE_TYPES
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid alert_on values: {invalid}")
    existing = await db.fim_paths.find_one(
        {"path": body.path, "platform": body.platform, "tenantId": current_user.tenant_id}
    )
    if existing:
        raise HTTPException(status_code=409, detail="Path already monitored")
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "tenantId": current_user.tenant_id,
        "path": body.path,
        "platform": body.platform,
        "recursive": body.recursive,
        "check_interval_seconds": max(60, body.check_interval_seconds),
        "alert_on": list(set(body.alert_on)),
        "ignore_patterns": body.ignore_patterns,
        "enabled": True,
        "created_at": now,
        "updated_at": now,
        "created_by": current_user.email,
    }
    await db.fim_paths.insert_one(doc)
    _strip_id(doc)
    return doc


@router.put("/paths/{path_id}")
async def update_monitored_path(
    path_id: str,
    body: PathUpdate,
    current_user: TokenData = Depends(get_current_user),
):
    """Update FIM path configuration."""
    db = get_database()
    existing = await db.fim_paths.find_one(
        {"id": path_id, "tenantId": current_user.tenant_id}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Path not found")
    updates = {k: v for k, v in body.dict().items() if v is not None}
    if "alert_on" in updates:
        invalid = set(updates["alert_on"]) - CHANGE_TYPES
        if invalid:
            raise HTTPException(status_code=400, detail=f"Invalid alert_on values: {invalid}")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.fim_paths.update_one(
        {"id": path_id, "tenantId": current_user.tenant_id},
        {"$set": updates},
    )
    doc = await db.fim_paths.find_one({"id": path_id, "tenantId": current_user.tenant_id})
    _strip_id(doc)
    return doc


@router.delete("/paths/{path_id}", status_code=204)
async def delete_monitored_path(
    path_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Remove a path from FIM monitoring."""
    db = get_database()
    result = await db.fim_paths.delete_one(
        {"id": path_id, "tenantId": current_user.tenant_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Path not found")
    return None


@router.post("/paths/seed-defaults")
async def seed_default_paths(
    platform: str = Query(..., description="linux|windows|macos"),
    current_user: TokenData = Depends(get_current_user),
):
    """Seed default CIS-recommended paths for a platform."""
    db = get_database()
    if platform not in DEFAULT_PATHS:
        raise HTTPException(status_code=400, detail=f"platform must be one of: {list(DEFAULT_PATHS.keys())}")
    now = datetime.now(timezone.utc).isoformat()
    added = 0
    for path in DEFAULT_PATHS[platform]:
        exists = await db.fim_paths.find_one(
            {"path": path, "platform": platform, "tenantId": current_user.tenant_id}
        )
        if not exists:
            await db.fim_paths.insert_one({
                "id": str(uuid.uuid4()),
                "tenantId": current_user.tenant_id,
                "path": path,
                "platform": platform,
                "recursive": path.endswith("/") or path.endswith("\\"),
                "check_interval_seconds": 300,
                "alert_on": ["added", "modified", "deleted"],
                "ignore_patterns": [],
                "enabled": True,
                "created_at": now,
                "updated_at": now,
                "created_by": current_user.email,
            })
            added += 1
    return {"platform": platform, "added": added, "total_defaults": len(DEFAULT_PATHS[platform])}


@router.get("/alerts")
async def list_fim_alerts(
    agent_id: Optional[str] = Query(None),
    change_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    hours: int = Query(24, ge=1, le=720),
    limit: int = Query(200, ge=1, le=1000),
    current_user: TokenData = Depends(get_current_user),
):
    """List FIM change alerts for the tenant."""
    db = get_database()
    query: dict = {"tenantId": current_user.tenant_id}
    if agent_id:
        query["agent_id"] = agent_id
    if change_type:
        query["change_type"] = change_type
    if severity:
        query["severity"] = severity
    alerts = []
    async for doc in db.fim_alerts.find(query).sort("detected_at", -1).limit(limit):
        _strip_id(doc)
        alerts.append(doc)
    return alerts


@router.get("/stats")
async def fim_stats(current_user: TokenData = Depends(get_current_user)):
    """FIM statistics for the tenant."""
    db = get_database()
    total_paths = await db.fim_paths.count_documents(
        {"tenantId": current_user.tenant_id, "enabled": True}
    )
    total_alerts = await db.fim_alerts.count_documents(
        {"tenantId": current_user.tenant_id}
    )
    pipeline = [
        {"$match": {"tenantId": current_user.tenant_id}},
        {"$group": {"_id": "$change_type", "count": {"$sum": 1}}},
    ]
    by_type: dict = {}
    async for row in db.fim_alerts.aggregate(pipeline):
        by_type[row["_id"]] = row["count"]
    sev_pipeline = [
        {"$match": {"tenantId": current_user.tenant_id}},
        {"$group": {"_id": "$severity", "count": {"$sum": 1}}},
    ]
    by_severity: dict = {}
    async for row in db.fim_alerts.aggregate(sev_pipeline):
        by_severity[row["_id"]] = row["count"]
    agents_monitored = await db.fim_paths.distinct(
        "agent_id", {"tenantId": current_user.tenant_id}
    )
    return {
        "total_monitored_paths": total_paths,
        "total_alerts": total_alerts,
        "by_change_type": by_type,
        "by_severity": by_severity,
        "agents_monitored": len([a for a in agents_monitored if a]),
    }
