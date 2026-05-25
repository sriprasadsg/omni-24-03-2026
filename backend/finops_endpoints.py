from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, List
from finops_service import finops_service
from rbac_utils import require_permission

_FINOPS_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}

router = APIRouter(prefix="/api/finops", tags=["FinOps & Cost Optimization"])

@router.get("/costs")
async def get_costs(
    current_user: dict = Depends(require_permission("view:reporting"))
):
    """
    Get current cost snapshot and history.
    """
    snapshot = await finops_service.calculate_current_spend()
    history  = await finops_service.get_cost_history()
    forecast = await finops_service.get_cost_forecast()
    
    return {
        "snapshot": snapshot,
        "history": history,
        "forecast": forecast
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

@router.post("/recalculate/{tenant_id}")
async def recalculate_costs(
    tenant_id: str,
    current_user: dict = Depends(require_permission("manage:system"))
):
    """
    Recalculate costs for a specific tenant.
    """
    caller_role = current_user.get("role", "") if isinstance(current_user, dict) else getattr(current_user, "role", "")
    caller_tenant = current_user.get("tenantId") or current_user.get("tenant_id") if isinstance(current_user, dict) else getattr(current_user, "tenant_id", None)
    if caller_role not in _FINOPS_SUPER_ROLES and caller_tenant != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return finops_service.recalculate_tenant_costs(tenant_id)

@router.get("/pricing")
async def get_pricing(
    current_user: dict = Depends(require_permission("view:settings"))
):
    """Get service pricing configuration."""
    return finops_service.get_service_pricing()

@router.post("/pricing")
async def update_pricing_bulk(
    pricing: List[Dict[str, Any]],
    current_user: dict = Depends(require_permission("manage:settings"))
):
    """Bulk update service pricing."""
    pricing = pricing[:500]
    _REQUIRED = {"id", "name", "price", "unit", "category"}
    for entry in pricing:
        if not _REQUIRED.issubset(entry.keys()):
            raise HTTPException(status_code=400, detail=f"Each pricing entry must contain: {_REQUIRED}")
        try:
            price = float(entry["price"])
            if price < 0:
                raise ValueError
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="price must be a non-negative number")
    finops_service.service_pricing = pricing
    return pricing

@router.post("/pricing/service")
async def create_service(
    service_data: Dict[str, Any],
    current_user: dict = Depends(require_permission("manage:settings"))
):
    """Create a new service pricing entry."""
    return finops_service.create_service_pricing(service_data)

@router.patch("/pricing/service/{service_id}")
async def update_service(
    service_id: str,
    updates: Dict[str, Any],
    current_user: dict = Depends(require_permission("manage:settings"))
):
    """Update a specific service pricing."""
    return finops_service.update_service_pricing(service_id, updates)

@router.delete("/pricing/service/{service_id}")
async def delete_service(
    service_id: str,
    current_user: dict = Depends(require_permission("manage:settings"))
):
    """Delete a service pricing entry."""
    return finops_service.delete_service_pricing(service_id)

