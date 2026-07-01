from fastapi import APIRouter, Depends
from datetime import datetime, timezone, timedelta
from typing import Optional
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData
from tenant_context import set_tenant_id

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])

_ADMIN_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin"}


@router.get("/historical")
async def get_historical_data(current_user: TokenData = Depends(get_current_user)):
    """Compute 6-month historical trend data from live collections."""
    is_admin = getattr(current_user, "role", "") in _ADMIN_ROLES
    if is_admin:
        set_tenant_id(None)
    db = get_database()
    tenant_id = None if is_admin else getattr(current_user, "tenant_id", None)

    now = datetime.now(timezone.utc)
    alerts_data = []
    compliance_data = []
    vuln_data = []

    for i in range(5, -1, -1):
        month_start = (now - timedelta(days=30 * i)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        month_end = (now - timedelta(days=30 * (i - 1))).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) if i > 0 else now
        label = month_start.strftime("%b")
        start_iso = month_start.isoformat()
        end_iso = month_end.isoformat()

        def _q(extra: dict) -> dict:
            q = {"createdAt": {"$gte": start_iso, "$lte": end_iso}}
            if tenant_id:
                q["tenantId"] = tenant_id
            q.update(extra)
            return q

        critical = await db.alerts.count_documents(
            _q({"severity": {"$in": ["Critical", "critical"]}})
        )
        high = await db.alerts.count_documents(
            _q({"severity": {"$in": ["High", "high"]}})
        )
        medium = await db.alerts.count_documents(
            _q({"severity": {"$in": ["Medium", "medium"]}})
        )
        alerts_data.append({"date": label, "Critical": critical, "High": high, "Medium": medium})

        # Compliance: average complianceScore across all frameworks
        fw_query = {}
        if tenant_id:
            fw_query["tenantId"] = tenant_id
        frameworks = await db.compliance_frameworks.find(
            fw_query, {"_id": 0, "complianceScore": 1}
        ).to_list(length=200)
        if frameworks:
            scores = [f.get("complianceScore", 0) for f in frameworks if f.get("complianceScore") is not None]
            avg_score = round(sum(scores) / len(scores), 1) if scores else 85.0
        else:
            avg_score = 85.0
        compliance_data.append({"date": label, "score": avg_score})

        crit_vuln = await db.patches.count_documents(
            _q({"severity": {"$in": ["Critical", "critical"]}, "status": {"$in": ["Pending", "pending", "Open", "open"]}})
        )
        high_vuln = await db.patches.count_documents(
            _q({"severity": {"$in": ["High", "high"]}, "status": {"$in": ["Pending", "pending", "Open", "open"]}})
        )
        vuln_data.append({"date": label, "Critical": crit_vuln, "High": high_vuln})

    return {"alerts": alerts_data, "compliance": compliance_data, "vulnerabilities": vuln_data}


@router.get("/events")
async def get_event_analytics(
    tenant_id: Optional[str] = None,
    days: int = 30,
    current_user: TokenData = Depends(get_current_user),
):
    """
    Return event counts by type and time bucket.
    Tests: O9 — GET /api/analytics/events?tenant_id=X → Event counts by type/time
    """
    is_admin = getattr(current_user, "role", "") in _ADMIN_ROLES
    caller_tenant = getattr(current_user, "tenant_id", None)
    effective_tenant = (tenant_id if is_admin else caller_tenant) or caller_tenant

    db = get_database()
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=days)).isoformat()

    query = {"timestamp": {"$gte": start}}
    if effective_tenant:
        query["tenantId"] = effective_tenant

    pipeline = [
        {"$match": query},
        {"$group": {
            "_id": {"type": "$event_type", "day": {"$substr": ["$timestamp", 0, 10]}},
            "count": {"$sum": 1},
        }},
        {"$sort": {"_id.day": 1}},
    ]

    records = await db.security_events.aggregate(pipeline).to_list(length=500)

    by_type: dict = {}
    by_day: dict = {}
    for r in records:
        etype = r["_id"].get("type", "unknown")
        day = r["_id"].get("day", "")
        cnt = r["count"]
        by_type[etype] = by_type.get(etype, 0) + cnt
        by_day[day] = by_day.get(day, 0) + cnt

    return {
        "by_type": by_type,
        "by_day": [{"date": k, "count": v} for k, v in sorted(by_day.items())],
        "total": sum(by_type.values()),
        "period_days": days,
    }


@router.get("/bi")
async def get_bi_metrics(
    tenant_id: str = None,
    current_user: TokenData = Depends(get_current_user),
):
    """Get advanced BI metrics"""
    is_admin = getattr(current_user, "role", "") in _ADMIN_ROLES
    caller_tenant = getattr(current_user, "tenant_id", None)
    if tenant_id and not is_admin and tenant_id != caller_tenant:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Not authorized to access this tenant")
    effective_tenant = tenant_id if (tenant_id and is_admin) else caller_tenant
    db = get_database()
    from bi_analytics_service import get_bi_analytics_service
    service = get_bi_analytics_service(db)
    return await service.get_bi_metrics(effective_tenant)
