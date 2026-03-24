from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, List
from finops_service import finops_service
from rbac_utils import require_permission

router = APIRouter(prefix="/api/finops", tags=["FinOps & Cost Optimization"])

@router.get("/costs")
async def get_costs(
    current_user: dict = Depends(require_permission("view:reporting"))
):
    """
    Get current cost snapshot and history.
    """
    snapshot = finops_service.calculate_current_spend()
    history = finops_service.get_cost_history()
    forecast = finops_service.get_cost_forecast()
    
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
    """
    return finops_service.generate_ai_analysis(data)

@router.post("/recalculate/{tenant_id}")
async def recalculate_costs(
    tenant_id: str,
    current_user: dict = Depends(require_permission("manage:system"))
):
    """
    Recalculate costs for a specific tenant.
    """
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

