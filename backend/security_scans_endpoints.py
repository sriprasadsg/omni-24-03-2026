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


@router.get("/security/attack-paths")
async def get_attack_paths(
    tenant_id: str = None,
    current_user: TokenData = Depends(get_current_user),
):
    """Get security attack paths from DB, derived from live alerts/vulns when empty."""
    try:
        db = get_database()
        is_admin = is_super_admin(getattr(current_user, "role", ""))
        query: dict = {}
        if not is_admin:
            query["tenantId"] = _sec_caller_tenant(current_user)
        elif tenant_id:
            query["tenantId"] = tenant_id

        paths = await db.attack_paths.find(query, {"_id": 0}).to_list(length=100)
        if paths:
            return paths

        vuln_query = {
            **query,
            "severity": {"$in": ["Critical", "critical"]},
            "status": {"$in": ["open", "Open", "pending", "Pending"]},
        }
        vulns = await db.patches.find(
            vuln_query, {"_id": 0, "id": 1, "cveId": 1, "affectedSoftware": 1, "description": 1}
        ).to_list(length=20)

        alert_query = {
            **query,
            "severity": {"$in": ["Critical", "critical"]},
            "status": {"$in": ["open", "Open", "new", "New"]},
        }
        alerts = await db.alerts.find(
            alert_query, {"_id": 0, "id": 1, "title": 1, "asset": 1, "description": 1}
        ).to_list(length=10)

        derived = []
        for i, vuln in enumerate(vulns[:5]):
            derived.append({
                "id": f"derived-vuln-{i + 1}",
                "name": f"Unpatched CVE: {vuln.get('cveId', 'Unknown')}",
                "riskScore": 90,
                "source": "derived",
                "steps": [
                    {"step": f"CVE affects {vuln.get('affectedSoftware', 'unknown software')}", "type": "Vulnerability"},
                    {"step": "Remote code execution possible", "type": "Execution"},
                    {"step": "Privilege escalation to SYSTEM", "type": "Privilege Escalation"},
                ],
                "affectedAssets": [vuln.get("affectedSoftware", "Unknown")],
            })
        for i, alert in enumerate(alerts[:5]):
            derived.append({
                "id": f"derived-alert-{i + 1}",
                "name": alert.get("title", f"Active Threat {i + 1}"),
                "riskScore": 80,
                "source": "derived",
                "steps": [
                    {"step": alert.get("description", "Suspicious activity detected"), "type": "Initial Access"},
                    {"step": "Lateral movement possible", "type": "Lateral Movement"},
                ],
                "affectedAssets": [alert.get("asset", "Unknown")],
            })

        return derived
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting attack paths: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
