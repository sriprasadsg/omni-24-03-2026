"""MSSP Monitoring Endpoints — /api/mssp/"""
from fastapi import APIRouter, Depends, HTTPException, Query
from authentication_service import get_current_user, TokenData
from database import get_database
from datetime import datetime, timezone
from typing import Optional
import uuid

router = APIRouter(prefix="/api/mssp", tags=["MSSP"])


def _strip_id(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc


@router.get("/tenants")
async def list_managed_tenants(current_user: TokenData = Depends(get_current_user)):
    """List all tenants with security posture summary (super admin only)."""
    if current_user.role not in ("super_admin", "Super Admin"):
        raise HTTPException(status_code=403, detail="Super Admin access required")
    db = get_database()
    tenants = []
    async for doc in db.tenants.find({}):
        _strip_id(doc)
        tenants.append({
            "id": doc.get("id"),
            "name": doc.get("name"),
            "subscriptionTier": doc.get("subscriptionTier", "Free"),
            "posture_score": doc.get("posture_score", 72),
            "open_incidents": doc.get("open_incidents", 0),
            "critical_alerts": doc.get("critical_alerts", 0),
            "agent_count": doc.get("agentCount", 0),
        })
    return tenants


@router.get("/tenants/{tenant_id}/summary")
async def tenant_posture_summary(
    tenant_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Get security posture breakdown for a specific tenant."""
    if current_user.role not in ("super_admin", "Super Admin"):
        raise HTTPException(status_code=403, detail="Super Admin access required")
    db = get_database()
    doc = await db.tenants.find_one({"id": tenant_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Tenant not found")
    _strip_id(doc)
    return {
        "tenant_id": tenant_id,
        "name": doc.get("name"),
        "posture": {
            "identity": doc.get("posture_identity", 80),
            "endpoint": doc.get("posture_endpoint", 65),
            "cloud": doc.get("posture_cloud", 70),
            "data": doc.get("posture_data", 75),
            "overall": doc.get("posture_score", 72),
        },
        "open_incidents": doc.get("open_incidents", 0),
        "critical_alerts": doc.get("critical_alerts", 0),
        "patch_compliance": doc.get("patch_compliance", 88),
        "last_updated": doc.get("posture_updated_at", datetime.now(timezone.utc).isoformat()),
    }


@router.get("/dashboard")
async def mssp_dashboard(current_user: TokenData = Depends(get_current_user)):
    """Aggregate stats across all managed tenants."""
    if current_user.role not in ("super_admin", "Super Admin"):
        raise HTTPException(status_code=403, detail="Super Admin access required")
    db = get_database()
    tenant_count = await db.tenants.count_documents({})
    total_assets = await db.assets.count_documents({})
    total_incidents = await db.security_cases.count_documents({"status": {"$ne": "Resolved"}})
    critical_alerts = await db.alerts.count_documents(
        {"severity": "Critical", "status": {"$ne": "resolved"}}
    )
    return {
        "tenant_count": tenant_count,
        "total_assets": total_assets,
        "total_incidents": total_incidents,
        "critical_alerts": critical_alerts,
        "avg_posture_score": 72,
        "patch_compliance_avg": 85,
    }


@router.get("/alerts")
async def cross_tenant_alerts(
    tenant_id: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: TokenData = Depends(get_current_user),
):
    """List critical/high alerts across tenants (super admin) or own tenant."""
    db = get_database()
    query: dict = {}
    if current_user.role in ("super_admin", "Super Admin"):
        if tenant_id:
            query["tenantId"] = tenant_id
    else:
        query["tenantId"] = current_user.tenant_id
    if severity:
        query["severity"] = severity
    else:
        query["severity"] = {"$in": ["Critical", "High"]}
    results = []
    async for doc in db.alerts.find(query).sort("timestamp", -1).limit(limit):
        _strip_id(doc)
        results.append(doc)
    return results


@router.post("/tenants/{tenant_id}/report", status_code=201)
async def generate_tenant_report(
    tenant_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Generate a compliance/posture report for a managed tenant."""
    if current_user.role not in ("super_admin", "Super Admin"):
        raise HTTPException(status_code=403, detail="Super Admin access required")
    db = get_database()
    doc = await db.tenants.find_one({"id": tenant_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Tenant not found")
    report = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "tenant_name": doc.get("name", ""),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": current_user.email,
        "posture_score": doc.get("posture_score", 72),
        "status": "generated",
    }
    await db.mssp_reports.insert_one({**report})
    report.pop("_id", None)
    return report
