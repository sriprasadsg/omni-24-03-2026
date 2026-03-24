from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Dict, Any, List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from database import get_database
from data_warehouse_service import get_data_warehouse_service
from rbac_utils import require_permission

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
    tenant_id = current_user.tenant_id
    
    try:
        results = await service.query_analytics(tenant_id, table_name, query_params)
        return results
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/stats")
async def get_warehouse_stats(
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:reporting"))
):
    """
    Get high-level warehouse statistics.
    """
    service = get_data_warehouse_service(db)
    tenant_id = current_user.tenant_id
    
    return await service.get_aggregated_stats(tenant_id)
