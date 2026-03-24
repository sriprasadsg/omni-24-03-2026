from fastapi import APIRouter, Depends, HTTPException
from dr_service import dr_service
from tenant_context import get_tenant_id
from datetime import datetime

router = APIRouter(prefix="/dr", tags=["Disaster Recovery"])

@router.get("/status")
async def get_dr_status(tenant_id: str = Depends(get_tenant_id)):
    """Provides real-time Disaster Recovery health and RPO/RTO metrics."""
    try:
        status = await dr_service.get_dr_status(tenant_id)
        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/regions")
async def get_region_status(tenant_id: str = Depends(get_tenant_id)):
    """Provides detailed status of cloud regions and replication latency."""
    try:
        status = await dr_service.get_dr_status(tenant_id)
        return status["regions"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/trigger-failover/{region_id}")
async def trigger_failover(region_id: str, tenant_id: str = Depends(get_tenant_id)):
    """Simulates a Disaster Recovery failover to a target region."""
    # Logic: Validate permissions and current health, then initiate failover.
    return {
        "status": "In Progress",
        "targetRegion": region_id,
        "estimatedCompletion": "15 minutes",
        "incidentId": f"failover-{datetime.now().timestamp()}"
    }
