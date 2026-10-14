from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from finops_service import finops_service
from rbac_utils import require_permission, require_super_admin
from database import get_database

_FINOPS_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}

router = APIRouter(prefix="/api/finops", tags=["FinOps & Cost Optimization"])


@router.get("/costs/history")
async def get_cost_history_endpoint(
    tenant_id: Optional[str] = None,
    days: int = Query(30, ge=1, le=365),
    current_user: dict = Depends(require_permission("view:reporting")),
):
    """
    Return daily cost entries for the past N days (zero-filled).
    Tests: K2 — GET /api/finops/costs/history?tenant_id=X&days=30
    """
    db = get_database()
    caller_role = current_user.get("role", "") if isinstance(current_user, dict) else getattr(current_user, "role", "")
    caller_tenant = current_user.get("tenantId") or current_user.get("tenant_id") if isinstance(current_user, dict) else getattr(current_user, "tenant_id", None)
    # Only super-admins may cross tenant boundaries via the query param
    effective_tenant = (tenant_id if caller_role in _FINOPS_SUPER_ROLES else caller_tenant) or caller_tenant

    query: Dict[str, Any] = {}
    if caller_role not in _FINOPS_SUPER_ROLES:
        query["tenantId"] = effective_tenant  # always scope non-admins to their own tenant

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)

    pipeline = [
        {"$match": {**query, "timestamp": {"$gte": start.isoformat()}}},
        {"$group": {
            "_id": {"$substr": ["$timestamp", 0, 10]},
            "total": {"$sum": "$amount"},
        }},
        {"$sort": {"_id": 1}},
    ]

    records = await db.usage_records.aggregate(pipeline).to_list(length=days + 1)
    by_date = {r["_id"]: r["total"] for r in records}

    history = []
    for i in range(days):
        day = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        history.append({"date": day, "cost": round(by_date.get(day, 0.0), 2)})

    # K5: check budget alert
    total_spend = sum(e["cost"] for e in history)
    budget = None
    alert = False
    if effective_tenant:
        tenant_doc = await db.tenants.find_one({"id": effective_tenant}, {"budget": 1, "_id": 0})
        if tenant_doc:
            budget = tenant_doc.get("budget")
            if budget and total_spend > budget:
                alert = True

    return {"history": history, "total_spend": round(total_spend, 2), "budget": budget, "budget_exceeded": alert}


@router.post("/budget/update")
async def update_budget(
    amount: float = Query(..., ge=0),
    current_user: dict = Depends(require_permission("view:reporting")),
):
    """Set the monthly cloud-spend budget for the caller's tenant."""
    db = get_database()
    caller_tenant = (
        (current_user.get("tenantId") or current_user.get("tenant_id"))
        if isinstance(current_user, dict) else getattr(current_user, "tenant_id", None)
    )
    if not caller_tenant:
        raise HTTPException(status_code=403, detail="Tenant context required")
    await db.tenants.update_one({"id": caller_tenant}, {"$set": {"budget": amount}})
    return {"success": True, "budget": amount}


@router.get("/costs")
async def get_costs(
    tenant_id: Optional[str] = None,
    current_user: dict = Depends(require_permission("view:reporting")),
):
    """
    Get current cost snapshot and history.
    Tests: K1 — GET /api/finops/costs?tenant_id=X → {total_spend, by_service, trend}
    """
    caller_role = current_user.get("role", "") if isinstance(current_user, dict) else getattr(current_user, "role", "")
    caller_tenant = current_user.get("tenantId") or current_user.get("tenant_id") if isinstance(current_user, dict) else getattr(current_user, "tenant_id", None)
    # Only super-admins may specify a different tenant
    effective_tenant = (tenant_id if caller_role in _FINOPS_SUPER_ROLES else caller_tenant) or caller_tenant

    snapshot = await finops_service.calculate_current_spend(effective_tenant)
    history  = await finops_service.get_cost_history()
    forecast = await finops_service.get_cost_forecast()

    return {
        "snapshot": snapshot,
        "history": history,
        "forecast": forecast,
        "total_spend": snapshot.get("total_spend", 0),
        "by_service": snapshot.get("by_service", {}),
        "trend": history[-7:] if isinstance(history, list) else [],
    }

@router.get("/recommendations")
async def get_recommendations(
    current_user: dict = Depends(require_permission("view:system"))
):
    """
    Get cost optimization recommendations.
    """
    return finops_service.generate_recommendations()

@router.post("/analysis")
async def generate_analysis(
    data: Dict[str, Any],
    current_user: dict = Depends(require_permission("view:reporting"))
):
    """
    Generate AI-powered FinOps analysis.
    Injects tenantId from the authenticated user so anomaly alerts fire for the right tenant.
    """
    tenant_id = (
        current_user.get("tenantId") or current_user.get("tenant_id")
        if isinstance(current_user, dict)
        else getattr(current_user, "tenantId", None)
    )
    if tenant_id:
        data = {**data, "tenantId": tenant_id}
    return finops_service.generate_ai_analysis(data)

@router.post("/recalculate")
async def recalculate_costs_query(
    tenant_id: str = "",
    current_user: dict = Depends(require_permission("manage:system")),
):
    """
    Recalculate costs for a specific tenant.
    Accepts tenant_id as a query parameter (alias for /recalculate/{tenant_id}).
    """
    caller_role = current_user.get("role", "") if isinstance(current_user, dict) else getattr(current_user, "role", "")
    caller_tenant = current_user.get("tenantId") or current_user.get("tenant_id") if isinstance(current_user, dict) else getattr(current_user, "tenant_id", None)
    effective_tenant = tenant_id or caller_tenant or ""
    if caller_role not in _FINOPS_SUPER_ROLES and caller_tenant != effective_tenant:
        raise HTTPException(status_code=403, detail="Access denied")
    return finops_service.recalculate_tenant_costs(effective_tenant)


@router.post("/recalculate/{tenant_id}")
async def recalculate_costs(
    tenant_id: str,
    current_user: dict = Depends(require_permission("manage:system"))
):
    """Recalculate costs for a specific tenant (path-param form)."""
    caller_role = current_user.get("role", "") if isinstance(current_user, dict) else getattr(current_user, "role", "")
    caller_tenant = current_user.get("tenantId") or current_user.get("tenant_id") if isinstance(current_user, dict) else getattr(current_user, "tenant_id", None)
    if caller_role not in _FINOPS_SUPER_ROLES and caller_tenant != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return finops_service.recalculate_tenant_costs(tenant_id)

@router.get("/pricing")
async def get_pricing(
    current_user: dict = Depends(require_permission("view:settings"))
):
    """Get service pricing configuration (includes one $5+ entry per compliance framework)."""
    return await finops_service.get_service_pricing(get_database())

# Service pricing applies to every tenant, so its writes are platform super-admin only.
@router.post("/pricing")
async def update_pricing_bulk(
    pricing: List[Dict[str, Any]],
    current_user: dict = Depends(require_super_admin)
):
    """Bulk create/update service pricing (persisted; compliance framework prices >= $5)."""
    return await finops_service.save_service_pricing(get_database(), pricing[:500])

@router.post("/pricing/service")
async def create_service(
    service_data: Dict[str, Any],
    current_user: dict = Depends(require_super_admin)
):
    """Create a new service pricing entry."""
    return await finops_service.create_service_pricing(get_database(), service_data)

@router.patch("/pricing/service/{service_id}")
async def update_service(
    service_id: str,
    updates: Dict[str, Any],
    current_user: dict = Depends(require_super_admin)
):
    """Update a specific service pricing (a compliance framework's price stays >= $5)."""
    return await finops_service.update_service_pricing(get_database(), service_id, updates)

@router.delete("/pricing/service/{service_id}")
async def delete_service(
    service_id: str,
    current_user: dict = Depends(require_super_admin)
):
    """Delete a service pricing entry (compliance framework prices cannot be removed)."""
    return await finops_service.delete_service_pricing(get_database(), service_id)

