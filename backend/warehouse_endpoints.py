from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from database import get_database
from data_warehouse_service import get_data_warehouse_service
from rbac_utils import require_permission
import logging


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/warehouse", tags=["Data Warehouse"])

@router.post("/query")
async def query_warehouse(
    query_params: Dict[str, Any],
    table_name: str = Query(..., description="Analytics table name (e.g., daily_threat_stats)"),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:reporting"))
):
    """
    Execute a query against the analytics warehouse.
    """
    service = get_data_warehouse_service(db)
    tenant_id = getattr(current_user, "tenant_id", None) or (current_user.get("tenant_id") if isinstance(current_user, dict) else None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context not found")
    
    try:
        results = await service.query_analytics(tenant_id, table_name, query_params)
        return results
    except Exception:
        raise HTTPException(status_code=400, detail="Bad request")

@router.get("/stats")
async def get_warehouse_stats(
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:reporting"))
):
    """
    Get high-level warehouse statistics.
    """
    service = get_data_warehouse_service(db)
    tenant_id = getattr(current_user, "tenant_id", None) or (current_user.get("tenant_id") if isinstance(current_user, dict) else None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context not found")

    # Auto-seed ETL on first call so the dashboard is never empty
    stats = await service.get_aggregated_stats(tenant_id)
    if stats.get("total_threats_processed", 0) == 0 and stats.get("total_api_calls_analyzed", 0) == 0:
        try:
            await service.run_etl(tenant_id)
            stats = await service.get_aggregated_stats(tenant_id)
        except Exception as e:
            logger.debug("Warehouse ETL auto-seed failed (non-fatal): %s", e)
    return stats


@router.post("/etl")
async def trigger_etl(
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:reporting"))
):
    """Manually trigger a full ETL run for the current tenant."""
    service = get_data_warehouse_service(db)
    tenant_id = getattr(current_user, "tenant_id", None) or (current_user.get("tenant_id") if isinstance(current_user, dict) else None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context not found")
    result = await service.run_etl(tenant_id)
    return {"status": "complete", **result}
