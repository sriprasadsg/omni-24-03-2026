from fastapi import APIRouter, Depends, HTTPException
import logging
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from database import get_database
from datetime import datetime, timezone
from integration_service import get_integration_service
from ml_service import get_ml_service
from authentication_service import get_current_user
from auth_types import TokenData

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Advanced Analytics & Integrations"])

_SUPER_ADMIN_ROLES = {"Super Admin", "superadmin", "super_admin", "platform-admin"}


def _get_tenant(current_user: TokenData) -> Optional[str]:
    role = getattr(current_user, "role", "") or ""
    if role in _SUPER_ADMIN_ROLES:
        return None  # super admins operate across all tenants
    return getattr(current_user, "tenant_id", None)


# ── Pydantic models ───────────────────────────────────────────────────────────

class SIEMEvent(BaseModel):
    event_type: str = Field(..., max_length=100)
    severity: str = Field("info", max_length=20)
    details: Dict[str, Any] = {}
    platform: str = Field("splunk", max_length=50)

class CMDBSync(BaseModel):
    platform: str = Field("servicenow", max_length=50)

class TicketCreate(BaseModel):
    title: str = Field(..., max_length=500)
    description: str = Field("", max_length=10000)
    priority: str = Field("medium", max_length=20)
    platform: str = Field("jira", max_length=50)
    metadata: Dict[str, Any] = {}

class IntegrationConfigModel(BaseModel):
    type: str = Field(..., max_length=50)
    platform: str = Field(..., max_length=50)
    enabled: bool = True
    endpoint: Optional[str] = Field(None, max_length=2048)
    token: Optional[str] = Field(None, max_length=2048)
    instance_url: Optional[str] = Field(None, max_length=2048)
    auth_token: Optional[str] = Field(None, max_length=2048)

class PatchFailureRequest(BaseModel):
    patch_id: str = Field(..., max_length=100)
    asset_id: str = Field(..., max_length=100)

class RecommendActionRequest(BaseModel):
    patch_id: str = Field(..., max_length=100)
    failure_predictions: List[Dict[str, Any]] = Field(default_factory=list, max_items=500)


# ── Phase 8: Integration Endpoints ───────────────────────────────────────────

@router.post("/api/integrations/siem/send")
async def send_to_siem(
    data: SIEMEvent,
    current_user: TokenData = Depends(get_current_user)
):
    """Send event to SIEM platform."""
    try:
        db = get_database()
        integration_service = get_integration_service(db)
        result = await integration_service.send_to_siem(
            event_type=data.event_type,
            severity=data.severity,
            details=data.details,
            platform=data.platform,
        )
        return result
    except Exception as e:
        logger.error("Error sending to SIEM: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/api/integrations/cmdb/sync")
async def sync_to_cmdb(
    data: CMDBSync,
    current_user: TokenData = Depends(get_current_user)
):
    """Sync tenant assets to CMDB. Tenant scope is derived from the auth token."""
    try:
        db = get_database()
        integration_service = get_integration_service(db)
        tenant_id = _get_tenant(current_user)
        result = await integration_service.sync_assets_to_cmdb(
            platform=data.platform,
            tenant_id=tenant_id,
        )
        return result
    except Exception as e:
        logger.error("Error syncing to CMDB: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/api/integrations/ticketing/create")
async def create_ticket(
    data: TicketCreate,
    current_user: TokenData = Depends(get_current_user)
):
    """Create ticket in ticketing system."""
    try:
        db = get_database()
        integration_service = get_integration_service(db)
        result = await integration_service.create_ticket(
            title=data.title,
            description=data.description,
            priority=data.priority,
            platform=data.platform,
            metadata=data.metadata,
        )
        return result
    except Exception as e:
        logger.error("Error creating ticket: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/api/integrations/config")
async def configure_integration(
    data: IntegrationConfigModel,
    current_user: TokenData = Depends(get_current_user)
):
    """Configure external integration. Admin only."""
    role = getattr(current_user, "role", "") or ""
    if role not in _SUPER_ADMIN_ROLES | {"Admin", "admin"}:
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        db = get_database()
        integration_config = {
            "type": data.type,
            "platform": data.platform,
            "enabled": data.enabled,
            "endpoint": data.endpoint,
            "token": data.token,
            "instance_url": data.instance_url,
            "auth_token": data.auth_token,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.integration_configs.update_one(
            {"type": data.type, "platform": data.platform},
            {"$set": integration_config},
            upsert=True,
        )
        return {"success": True, "message": f"{data.type} integration for {data.platform} configured"}
    except Exception as e:
        logger.error("Error configuring integration: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Phase 9: ML/AI Endpoints ──────────────────────────────────────────────────

@router.post("/api/ml/predict-failure")
async def predict_patch_failure(
    data: PatchFailureRequest,
    current_user: TokenData = Depends(get_current_user)
):
    """Predict patch deployment failure probability."""
    try:
        db = get_database()
        ml_service = get_ml_service(db)
        prediction = await ml_service.predict_patch_failure(
            patch_id=data.patch_id,
            asset_id=data.asset_id,
        )
        return prediction
    except Exception as e:
        logger.error("Error predicting failure: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/api/ml/detect-anomalies")
async def detect_anomalies(
    lookback_days: int = 7,
    current_user: TokenData = Depends(get_current_user)
):
    """Detect anomalies in patch deployment patterns. Tenant scope from auth token."""
    try:
        db = get_database()
        ml_service = get_ml_service(db)
        tenant_id = _get_tenant(current_user)
        anomalies = await ml_service.detect_anomalies(
            tenant_id=tenant_id,
            lookback_days=lookback_days,
        )
        return anomalies
    except Exception as e:
        logger.error("Error detecting anomalies: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/api/ml/recommend-action")
async def recommend_autonomous_action(
    data: RecommendActionRequest,
    current_user: TokenData = Depends(get_current_user)
):
    """Recommend autonomous deployment action."""
    try:
        db = get_database()
        ml_service = get_ml_service(db)
        recommendation = await ml_service.recommend_autonomous_action(
            patch_id=data.patch_id,
            failure_predictions=data.failure_predictions,
        )
        return recommendation
    except Exception as e:
        logger.error("Error generating recommendation: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Phase 7: Health Check (public — for load-balancer/monitoring) ─────────────

@router.get("/api/system/health")
async def get_system_health():
    """System health metrics for load balancing/monitoring."""
    try:
        db = get_database()
        active_deployments = await db.patch_deployment_jobs.count_documents(
            {"status": {"$in": ["scheduled", "in_progress"]}}
        )
        total_assets = await db.assets.count_documents({})
        pending_patches = await db.patches.count_documents({"status": "Pending"})
        return {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metrics": {
                "active_deployments": active_deployments,
                "total_assets": total_assets,
                "pending_patches": pending_patches,
                "database_status": "connected",
            },
            "version": "1.0.0",
        }
    except Exception as e:
        logger.error("Error getting health: %s", e)
        raise HTTPException(status_code=503, detail="Internal server error")
