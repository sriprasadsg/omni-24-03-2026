import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData
from rbac_utils import is_super_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


def _sec_caller_tenant(current_user) -> str:
    tid = getattr(current_user, "tenant_id", None) or None
    if not tid:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return tid


@router.post("/vulnerability-scans/schedule")
async def schedule_vulnerability_scan(
    data: dict,
    current_user: TokenData = Depends(get_current_user),
):
    """Schedule a vulnerability scan against one or more assets."""
    try:
        db = get_database()
        job = {
            "id": f"job-{uuid.uuid4()}",
            "type": "Vulnerability Scan",
            "status": "Queued",
            "progress": 0,
            "targetAssets": data.get("assetIds", []),
            "scanType": data.get("scanType", "Immediate"),
            "scheduleTime": data.get("scheduleTime") or datetime.now(timezone.utc).isoformat(),
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "createdBy": getattr(current_user, "username", "unknown"),
            "tenantId": getattr(current_user, "tenant_id", None),
            "log": ["Job created"],
        }
        await db.vulnerability_scan_jobs.insert_one(job)
        job.pop("_id", None)
        return job
    except Exception as e:
        logger.error("Error scheduling scan: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/assets/{asset_id}/scan")
async def trigger_asset_scan(
    asset_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Trigger an immediate vulnerability scan for a single asset."""
    try:
        db = get_database()
        is_admin = is_super_admin(getattr(current_user, "role", ""))
        asset_filter: dict = {"id": asset_id}
        if not is_admin:
            asset_filter["tenantId"] = _sec_caller_tenant(current_user)

        timestamp = datetime.now(timezone.utc).isoformat()
        result = await db.assets.update_one(asset_filter, {"$set": {"lastScanned": timestamp}})
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Asset not found")
        return {"success": True, "lastScanned": timestamp}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error triggering scan: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")

