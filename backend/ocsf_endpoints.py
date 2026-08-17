"""OCSF Output Format — findings and cloud checks in OCSF 1.0 schema."""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from database import get_database
from auth_types import TokenData
from tenant_context import get_tenant_id
from rbac_service import rbac_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ocsf", tags=["OCSF Export"])


def _to_epoch(iso_str: str) -> int:
    try:
        return int(datetime.fromisoformat(iso_str.replace("Z", "+00:00")).timestamp())
    except Exception:
        logger.warning("Failed to parse OCSF timestamp %r, using current time", iso_str)
        return int(datetime.now(timezone.utc).timestamp())


severity_map = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}


@router.get("/findings")
async def ocsf_findings(severity: str = Query(None), limit: int = Query(100, ge=1, le=1000), current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard"))):
    db = get_database()
    tenant_id = get_tenant_id()
    query = {"tenantId": tenant_id}
    if severity:
        query["severity"] = severity
    findings = await db.cloud_findings.find(query, {"_id": 0}).sort("created_at", -1).to_list(length=limit)
    ocsf_items = []
    for f in findings:
        sev_id = severity_map.get(f.get("severity", "medium"), 3)
        ocsf_items.append({
            "class_uid": 2004,
            "category_uid": 2,
            "type_uid": 200401,
            "severity_id": sev_id,
            "severity": f.get("severity", "medium"),
            "finding": {"uid": f.get("id", ""), "title": f.get("title", "")},
            "time": _to_epoch(f.get("created_at", "")),
            "metadata": {"version": "1.0.0", "product": {"name": "OmniAgent Platform"}},
            "resources": [{"uid": f.get("accountId", ""), "type": f.get("provider", "aws")}] if f.get("accountId") else [],
        })
    return {"items": ocsf_items, "count": len(ocsf_items)}


@router.get("/cloud-checks")
async def ocsf_cloud_checks(provider: str = Query(None), limit: int = Query(100, ge=1, le=1000), current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard"))):
    db = get_database()
    tenant_id = get_tenant_id()
    query = {"tenantId": tenant_id}
    if provider:
        query["provider"] = provider
    results = await db.cloud_check_results.find(query, {"_id": 0}).sort("checked_at", -1).to_list(length=limit)
    severity_map = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}
    ocsf_items = []
    for r in results:
        sev_id = severity_map.get(r.get("severity", "medium"), 3)
        ocsf_items.append({
            "class_uid": 5001,
            "category_uid": 5,
            "type_uid": 500101,
            "severity_id": sev_id,
            "severity": r.get("severity", "medium"),
            "finding": {"uid": r.get("checkId", ""), "title": r.get("checkName", "")},
            "time": _to_epoch(r.get("checked_at", "")),
            "metadata": {"version": "1.0.0", "product": {"name": "OmniAgent Platform"}},
            "status": r.get("result", "unknown"),
            "remediation": {"desc": r.get("remediation", "")},
        })
    return {"items": ocsf_items, "count": len(ocsf_items)}
