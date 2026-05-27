"""
APM API Endpoints

Provides API for accessing performance metrics and monitoring data.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Dict
from motor.motor_asyncio import AsyncIOMotorDatabase

from database import get_database
from apm_service import get_apm_service
from rbac_utils import require_permission

_APM_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}

router = APIRouter(prefix="/api/apm", tags=["APM"])


# Request/Response Models
class PerformanceMetric(BaseModel):
    endpoint: str
    total_requests: int
    error_count: int
    error_rate: float
    slow_count: int
    latency: Dict[str, float]
    throughput_per_min: float
    health_status: str


# Endpoints
@router.get("/health")
async def get_system_health(
    db: AsyncIOMotorDatabase = Depends(get_database),
    _current_user: dict = Depends(require_permission("view:system"))
):
    """Get overall system health status (last 5 minutes)"""
    service = get_apm_service(db)
    return await service.get_system_health()


@router.get("/endpoints")
async def get_endpoint_metrics(
    time_window_minutes: int = 60,
    db: AsyncIOMotorDatabase = Depends(get_database),
    _current_user: dict = Depends(require_permission("view:system"))
):
    """Get performance metrics for all endpoints"""
    service = get_apm_service(db)
    return await service.get_endpoint_metrics(time_window_minutes)


@router.get("/endpoints/slowest")
async def get_slowest_endpoints(
    limit: int = 10,
    time_window_minutes: int = 60,
    db: AsyncIOMotorDatabase = Depends(get_database),
    _current_user: dict = Depends(require_permission("view:system"))
):
    """Get slowest endpoints by p95 latency"""
    service = get_apm_service(db)
    return await service.get_slowest_endpoints(limit, time_window_minutes)


@router.get("/endpoints/errors")
async def get_error_prone_endpoints(
    limit: int = 10,
    time_window_minutes: int = 60,
    db: AsyncIOMotorDatabase = Depends(get_database),
    _current_user: dict = Depends(require_permission("view:system"))
):
    """Get endpoints with highest error rates"""
    service = get_apm_service(db)
    return await service.get_error_prone_endpoints(limit, time_window_minutes)


@router.get("/database")
async def get_database_performance(
    time_window_minutes: int = 60,
    db: AsyncIOMotorDatabase = Depends(get_database),
    _current_user: dict = Depends(require_permission("view:system"))
):
    """Get database query performance metrics"""
    service = get_apm_service(db)
    return await service.get_database_performance(time_window_minutes)


@router.get("/external-apis")
async def get_external_api_performance(
    time_window_minutes: int = 60,
    db: AsyncIOMotorDatabase = Depends(get_database),
    _current_user: dict = Depends(require_permission("view:system"))
):
    """Get external API call performance"""
    service = get_apm_service(db)
    return await service.get_external_api_performance(time_window_minutes)


@router.get("/trend/{endpoint:path}")
async def get_performance_trend(
    endpoint: str,
    hours: int = 24,
    db: AsyncIOMotorDatabase = Depends(get_database),
    _current_user: dict = Depends(require_permission("view:system"))
):
    """Get performance trend for a specific endpoint"""
    service = get_apm_service(db)
    return await service.get_performance_trend(endpoint, hours)


@router.get("/alerts")
async def get_apm_alerts(
    limit: int = 50,
    acknowledged: Optional[bool] = None,
    db: AsyncIOMotorDatabase = Depends(get_database),
    _current_user: dict = Depends(require_permission("view:system"))
):
    """Get APM alerts and SLA violations"""
    query = {}
    if acknowledged is not None:
        query["acknowledged"] = acknowledged

    alerts = []
    async for alert in db.apm_alerts.find(query).sort("created_at", -1).limit(limit):
        alert["id"] = str(alert.pop("_id"))
        alerts.append(alert)

    return alerts


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("manage:system"))
):
    """Acknowledge an APM alert"""
    actor = getattr(current_user, "username", None) or (
        current_user.get("email") if isinstance(current_user, dict) else None
    )
    caller_role = current_user.get("role", "") if isinstance(current_user, dict) else getattr(current_user, "role", "")
    caller_tenant = current_user.get("tenant_id") if isinstance(current_user, dict) else getattr(current_user, "tenant_id", None)
    alert_filter: dict = {"_id": alert_id}
    if caller_role not in _APM_SUPER_ROLES and caller_tenant:
        alert_filter["tenantId"] = caller_tenant
    result = await db.apm_alerts.update_one(
        alert_filter,
        {"$set": {"acknowledged": True, "acknowledged_by": actor}}
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Alert not found")

    return {"message": "Alert acknowledged"}


@router.get("/sla-violations")
async def check_sla_violations(
    db: AsyncIOMotorDatabase = Depends(get_database),
    _current_user: dict = Depends(require_permission("view:system"))
):
    """Check for current SLA violations"""
    service = get_apm_service(db)
    return await service.check_sla_violations()
