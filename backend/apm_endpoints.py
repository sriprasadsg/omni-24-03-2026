"""
APM API Endpoints

Provides API for accessing performance metrics and monitoring data.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from database import get_database
from apm_service import get_apm_service
from rbac_utils import require_permission

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
    current_user: dict = Depends(require_permission("view:system"))
):
    """
    Get overall system health status
    
    Returns health metrics for the last 5 minutes
    """
    service = get_apm_service(db)
    health = await service.get_system_health()
    return health


@router.get("/endpoints")
async def get_endpoint_metrics(
    time_window_minutes: int = 60,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:system"))
):
    """
    Get performance metrics for all endpoints
    
    Returns latency percentiles, error rates, and throughput
    """
    service = get_apm_service(db)
    metrics = await service.get_endpoint_metrics(time_window_minutes)
    return metrics


@router.get("/endpoints/slowest")
async def get_slowest_endpoints(
    limit: int = 10,
    time_window_minutes: int = 60,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:system"))
):
    """
    Get slowest endpoints by p95 latency
    
    Useful for identifying performance bottlenecks
    """
    service = get_apm_service(db)
    endpoints = await service.get_slowest_endpoints(limit, time_window_minutes)
    return endpoints


@router.get("/endpoints/errors")
async def get_error_prone_endpoints(
    limit: int = 10,
    time_window_minutes: int = 60,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:system"))
):
    """
    Get endpoints with highest error rates
    
    Useful for identifying reliability issues
    """
    service = get_apm_service(db)
    endpoints = await service.get_error_prone_endpoints(limit, time_window_minutes)
    return endpoints


@router.get("/database")
async def get_database_performance(
    time_window_minutes: int = 60,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:system"))
):
    """
    Get database query performance metrics
    
    Returns slow queries and collection-level statistics
    """
    service = get_apm_service(db)
    performance = await service.get_database_performance(time_window_minutes)
    return performance


@router.get("/external-apis")
async def get_external_api_performance(
    time_window_minutes: int = 60,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:system"))
):
    """
    Get external API call performance
    
    Returns latency and success rates for external services
    """
    service = get_apm_service(db)
    performance = await service.get_external_api_performance(time_window_minutes)
    return performance


@router.get("/trend/{endpoint:path}")
async def get_performance_trend(
    endpoint: str,
    hours: int = 24,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:system"))
):
    """
    Get performance trend for a specific endpoint
    
    Returns hourly aggregated metrics over the specified time period
    """
    service = get_apm_service(db)
    trend = await service.get_performance_trend(endpoint, hours)
    return trend


@router.get("/alerts")
async def get_apm_alerts(
    limit: int = 50,
    acknowledged: Optional[bool] = None,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:system"))
):
    """
    Get APM alerts
    
    Returns performance alerts and SLA violations
    """
    query = {}
    if acknowledged is not None:
        query["acknowledged"] = acknowledged
    
    cursor = db.apm_alerts.find(query).sort("created_at", -1).limit(limit)
    
    alerts = []
    async for alert in cursor:
        alert["id"] = str(alert.pop("_id"))
        alerts.append(alert)
    
    return alerts


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("manage:system"))
):
    """
    Acknowledge an APM alert
    
    Marks the alert as acknowledged
    """
    result = await db.apm_alerts.update_one(
        {"_id": alert_id},
        {"$set": {"acknowledged": True, "acknowledged_by": current_user.get("email")}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    return {"message": "Alert acknowledged"}


@router.get("/sla-violations")
async def check_sla_violations(
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:system"))
):
    """
    Check for current SLA violations
    
    Returns active violations based on error rates and latency
    """
    service = get_apm_service(db)
    violations = await service.check_sla_violations()
    return violations
