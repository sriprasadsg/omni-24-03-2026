import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException
from dr_service import dr_service
from tenant_context import get_tenant_id
from authentication_service import get_current_user
from database import get_database
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dr", tags=["Disaster Recovery"])

_DR_FAILOVER_ROLES = {"Super Admin", "super_admin", "platform-admin", "admin"}

@router.get("/status")
async def get_dr_status(tenant_id: str = Depends(get_tenant_id), _user=Depends(get_current_user)):
    """Provides real-time Disaster Recovery health and RPO/RTO metrics."""
    try:
        status = await dr_service.get_dr_status(tenant_id)
        return status
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/regions")
async def get_region_status(tenant_id: str = Depends(get_tenant_id), _user=Depends(get_current_user)):
    """Provides detailed status of cloud regions and replication latency."""
    try:
        status = await dr_service.get_dr_status(tenant_id)
        return status["regions"]
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/trigger-failover/{region_id}")
async def trigger_failover(region_id: str, tenant_id: str = Depends(get_tenant_id), _user=Depends(get_current_user)):
    caller_role = getattr(_user, "role", "") if not isinstance(_user, dict) else _user.get("role", "")
    if caller_role not in _DR_FAILOVER_ROLES:
        raise HTTPException(status_code=403, detail="Only administrators can trigger disaster recovery failover")
    """Initiates a Disaster Recovery failover to the target region."""
    try:
        db = get_database()
        incident_id = f"failover-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        failover_record = {
            "id": incident_id,
            "tenantId": tenant_id,
            "targetRegion": region_id,
            "status": "In Progress",
            "initiatedAt": now,
            "type": "failover",
        }
        await db.dr_incidents.insert_one(failover_record)

        # Dispatch failover instruction to agents in the target region
        agents = await db.agents.find(
            {"tenantId": tenant_id, "status": "online"},
            {"_id": 0, "id": 1}
        ).to_list(length=50)
        for agent in agents:
            await db.agent_instructions.insert_one({
                "agentId": agent["id"],
                "tenantId": tenant_id,
                "instruction": f"initiate_failover_to_region:{region_id}",
                "incidentId": incident_id,
                "status": "pending",
                "createdAt": now,
            })

        logger.info("DR failover to %s initiated for tenant %s — incident %s", region_id, tenant_id, incident_id)
        return {
            "status": "In Progress",
            "targetRegion": region_id,
            "estimatedCompletion": "15 minutes",
            "incidentId": incident_id,
            "agentsNotified": len(agents),
        }
    except Exception as e:
        logger.error("DR failover trigger failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
