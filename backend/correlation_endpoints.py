"""
Correlation API Endpoints

Provides SIEM correlation and attack pattern detection capabilities.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase

from database import get_database
from correlation_engine import get_correlation_engine, _BUILTIN_ATTACK_PATTERNS
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


@router.post("/run")
async def run_correlation(
    request: CorrelateRequest,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("manage:security_cases")),
):
    """
    Manually trigger a full correlation run for a tenant.
    Identical to /analyze but explicitly labelled as a forced run so operators
    can use it without confusion with the periodic automatic run.
    """
    engine = get_correlation_engine(db)
    correlations = await engine.correlate_events(
        tenant_id=request.tenant_id,
        time_window_minutes=request.time_window_minutes,
    )
    return {
        "triggered_by": "manual",
        "tenant_id": request.tenant_id,
        "correlations_found": len(correlations),
        "correlations": [Correlation(**c) for c in correlations],
    }


@router.post("/false-positive/{correlation_id}")
async def mark_false_positive(
    correlation_id: str,
    body: dict = {},
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("manage:security_cases")),
):
    """Mark a correlation as a false positive to auto-tune its detection threshold."""
    correlation = await db.correlations.find_one({"_id": correlation_id})
    if not correlation:
        raise HTTPException(status_code=404, detail="Correlation not found")
    pattern_id = correlation.get("pattern_id") or correlation.get("mitre_attack", "")
    tenant_id = correlation.get("tenant_id", body.get("tenant_id", ""))
    if pattern_id and tenant_id:
        engine = get_correlation_engine(db)
        await engine.record_false_positive(tenant_id=tenant_id, pattern_id=pattern_id)
    await db.correlations.update_one(
        {"_id": correlation_id},
        {"$set": {"false_positive": True, "reviewed_by": getattr(current_user, "email", str(current_user))}},
    )
    return {"correlation_id": correlation_id, "pattern_id": pattern_id, "status": "marked_false_positive"}


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


# ── Attack Pattern Management ─────────────────────────────────────────────────

class AttackPatternUpsert(BaseModel):
    pattern_id: str
    name: str
    events: List[str]
    threshold: int
    time_window_minutes: int
    mitre: Optional[str] = ""
    severity: Optional[str] = "high"
    enabled: Optional[bool] = True


@router.get("/patterns/list")
async def list_attack_patterns(
    db: AsyncIOMotorDatabase = Depends(get_database),
    _current_user: dict = Depends(require_permission("view:security")),
):
    """
    Return all effective attack patterns — DB overrides merged over builtins.
    Includes a `source` field ('builtin' | 'custom') so the UI can distinguish them.
    """
    engine = get_correlation_engine(db)
    if not engine._patterns_loaded:
        await engine._load_attack_patterns_from_db()

    # Collect DB patterns for merge tracking
    db_pattern_ids = set()
    async for doc in db.signature_library.find({"version_type": "attack_pattern"}):
        db_pattern_ids.add(doc.get("pattern_id"))

    result = []
    for pid, pat in engine.attack_patterns.items():
        entry = dict(pat)
        entry["pattern_id"] = pid
        entry["source"] = "custom" if pid in db_pattern_ids else "builtin"
        result.append(entry)
    return result


@router.put("/patterns/{pattern_id}")
async def upsert_attack_pattern(
    pattern_id: str,
    body: AttackPatternUpsert,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("manage:security_cases")),
):
    """
    Create or update an attack pattern in the signature_library collection.
    The running engine reloads on the next correlation cycle.
    """
    now = datetime.now(timezone.utc).isoformat()
    doc = body.model_dump()
    doc["pattern_id"] = pattern_id
    doc["version_type"] = "attack_pattern"
    doc["updated_at"] = now
    doc["updated_by"] = getattr(current_user, "username", str(current_user))

    await db.signature_library.update_one(
        {"version_type": "attack_pattern", "pattern_id": pattern_id},
        {"$set": doc},
        upsert=True,
    )
    # Force the in-memory engine to reload on next cycle
    engine = get_correlation_engine(db)
    engine._patterns_loaded = False

    return {"pattern_id": pattern_id, "status": "upserted", "updated_at": now}


@router.delete("/patterns/{pattern_id}")
async def delete_attack_pattern(
    pattern_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("manage:security_cases")),
):
    """
    Remove a custom pattern from DB.  Builtin patterns are restored automatically
    (they live in code, not the DB).
    """
    if pattern_id in _BUILTIN_ATTACK_PATTERNS:
        raise HTTPException(
            status_code=400,
            detail=f"'{pattern_id}' is a builtin pattern — disable it instead of deleting.",
        )
    result = await db.signature_library.delete_one(
        {"version_type": "attack_pattern", "pattern_id": pattern_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Custom pattern not found")
    engine = get_correlation_engine(db)
    engine._patterns_loaded = False
    return {"pattern_id": pattern_id, "status": "deleted"}


@router.patch("/patterns/{pattern_id}/disable")
async def disable_attack_pattern(
    pattern_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: dict = Depends(require_permission("manage:security_cases")),
):
    """Disable a builtin or custom pattern without deleting it."""
    now = datetime.now(timezone.utc).isoformat()
    await db.signature_library.update_one(
        {"version_type": "attack_pattern", "pattern_id": pattern_id},
        {"$set": {"enabled": False, "updated_at": now}},
        upsert=True,
    )
    engine = get_correlation_engine(db)
    engine._patterns_loaded = False
    return {"pattern_id": pattern_id, "status": "disabled"}
