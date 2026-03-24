"""
Correlation API Endpoints

Provides SIEM correlation and attack pattern detection capabilities.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from database import get_database
from correlation_engine import get_correlation_engine
from rbac_utils import require_permission

router = APIRouter(prefix="/api/correlations", tags=["SIEM Correlation"])

def _get(user, key, default=None):
    """Get a field from either a dict or Pydantic user object."""
    if isinstance(user, dict):
        return user.get(key, default)
    return getattr(user, key, default)


# Request/Response Models
class CorrelateRequest(BaseModel):
    tenant_id: str
    time_window_minutes: int = 60


class Correlation(BaseModel):
    id: str
    tenant_id: str
    type: str
    pattern: str
    event_count: int
    confidence: float
    severity: str
    detected_at: str


# Endpoints
@router.post("/analyze", response_model=List[Correlation])
async def analyze_correlations(
    request: CorrelateRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:security"))
):
    """
    Analyze security events and detect correlations/attack patterns
    
    Returns list of detected correlations with confidence scores
    """
    engine = get_correlation_engine(db)
    
    correlations = await engine.correlate_events(
        tenant_id=request.tenant_id,
        time_window_minutes=request.time_window_minutes
    )
    
    return [Correlation(**c) for c in correlations]


@router.get("/", response_model=List[Correlation])
async def get_correlations(
    tenant_id: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 50,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:security"))
):
    """
    Get recent correlations
    
    Returns list of correlations filtered by tenant and severity
    """
    if not tenant_id and _get(current_user, 'role') != "Super Admin":
        tenant_id = _get(current_user, "tenantId")
    
    engine = get_correlation_engine(db)
    correlations = await engine.get_correlations(
        tenant_id=tenant_id or _get(current_user, "tenantId"),
        limit=limit,
        severity=severity
    )
    
    return [Correlation(**c) for c in correlations]


@router.get("/stats")
async def get_correlation_stats(
    tenant_id: Optional[str] = None,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:security"))
):
    """
    Get correlation statistics
    
    Returns aggregated stats on correlations by severity
    """
    if not tenant_id and _get(current_user, 'role') != "Super Admin":
        tenant_id = _get(current_user, "tenantId")
    
    engine = get_correlation_engine(db)
    stats = await engine.get_correlation_stats(
        tenant_id=tenant_id or _get(current_user, "tenantId")
    )
    
    return stats


@router.get("/{correlation_id}")
async def get_correlation_details(
    correlation_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("view:security"))
):
    """
    Get detailed information about a specific correlation
    
    Includes all related events and analysis
    """
    correlation = await db.correlations.find_one({"_id": correlation_id})
    
    if not correlation:
        raise HTTPException(status_code=404, detail="Correlation not found")
    
    # Fetch related events
    event_ids = correlation.get("event_ids", [])
    events = []
    
    if event_ids:
        cursor = db.security_events.find({"_id": {"$in": event_ids}})
        async for event in cursor:
            event["id"] = str(event.pop("_id"))
            events.append(event)
    
    correlation["id"] = str(correlation.pop("_id"))
    correlation["related_events"] = events
    
    return correlation
