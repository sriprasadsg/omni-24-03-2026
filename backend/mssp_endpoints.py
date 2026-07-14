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


def _derive_health(compliance_score: int, open_incidents: int, critical_alerts: int) -> str:
    if critical_alerts > 0 or compliance_score < 50:
        return "critical"
    if open_incidents > 0 or compliance_score < 80:
        return "warning"
    return "healthy"


@router.get("/overview")
async def mssp_overview(current_user: TokenData = Depends(get_current_user)):
    """Per-tenant health roll-up for the MSSP dashboard (super admin only)."""
    if current_user.role not in ("super_admin", "Super Admin"):
        raise HTTPException(status_code=403, detail="Super Admin access required")
    db = get_database()

    # Live agent counts per tenant
    agent_counts: dict = {}
    async for row in db.agents.aggregate([
        {"$group": {"_id": "$tenantId", "n": {"$sum": 1}}}
    ]):
        agent_counts[row["_id"]] = row["n"]

    # Compliance score per tenant from asset_compliance (Compliant ratio)
    compliance: dict = {}
    async for row in db.asset_compliance.aggregate([
        {"$group": {
            "_id": "$tenantId",
            "total": {"$sum": 1},
            "compliant": {"$sum": {"$cond": [{"$eq": ["$status", "Compliant"]}, 1, 0]}},
        }}
    ]):
        total = row.get("total", 0)
        compliance[row["_id"]] = round((row.get("compliant", 0) / total) * 100) if total else 100

    tenants = []
    healthy = warning = critical = total_agents = 0
    async for doc in db.tenants.find({}):
        tid = doc.get("id")
        agent_count = agent_counts.get(tid, 0)
        comp = compliance.get(tid, 100)
        open_incidents = await db.security_cases.count_documents(
            {"tenantId": tid, "status": {"$ne": "Resolved"}}
        )
        critical_alerts = await db.alerts.count_documents(
            {"tenantId": tid, "severity": "Critical", "status": {"$ne": "resolved"}}
        )
        health = _derive_health(comp, open_incidents, critical_alerts)
        if health == "healthy":
            healthy += 1
        elif health == "warning":
            warning += 1
        else:
            critical += 1
        total_agents += agent_count
        tenants.append({
            "id": tid,
            "tenant_name": doc.get("name", ""),
            "health_status": health,
            "agent_count": agent_count,
            "open_incidents": open_incidents,
            "critical_alerts": critical_alerts,
            "compliance_score": comp,
            "last_activity": doc.get("created_at", ""),
        })

    return {
        "tenants": tenants,
        "total_tenants": len(tenants),
        "healthy_count": healthy,
        "warning_count": warning,
        "critical_count": critical,
        "total_agents": total_agents,
    }


@router.get("/alerts/aggregated")
async def aggregated_alerts(
    severity: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: TokenData = Depends(get_current_user),
):
    """Cross-tenant alert feed shaped for the MSSP dashboard."""
    db = get_database()
    query: dict = {}
    if current_user.role not in ("super_admin", "Super Admin"):
        query["tenantId"] = current_user.tenant_id
    if severity:
        query["severity"] = {"$regex": f"^{severity}$", "$options": "i"}

    tenant_names: dict = {}
    async for t in db.tenants.find({}, {"id": 1, "name": 1}):
        tenant_names[t.get("id")] = t.get("name", "")

    results = []
    async for doc in db.alerts.find(query).sort("timestamp", -1).limit(limit):
        results.append({
            "id": doc.get("id", str(doc.get("_id", ""))),
            "tenant_name": tenant_names.get(doc.get("tenantId"), doc.get("tenantId", "")),
            "severity": str(doc.get("severity", "low")).lower(),
            "event_type": doc.get("event_type") or doc.get("type", "alert"),
            "description": doc.get("description") or doc.get("message", ""),
            "timestamp": doc.get("timestamp", ""),
        })
    return results


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
