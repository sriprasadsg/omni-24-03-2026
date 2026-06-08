from fastapi import APIRouter, Depends, HTTPException, Body, Query
from typing import List, Any, Optional
from pydantic import BaseModel, Field
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData
from rbac_utils import require_permission
from datetime import datetime, timezone
import logging
import uuid

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alerts", tags=["Alerts"])

_SUPER_ADMIN_ROLES = {"Super Admin", "superadmin", "super_admin", "platform-admin"}

def _tenant_filter(user: TokenData) -> dict:
    role = getattr(user, "role", "") or ""
    if role in _SUPER_ADMIN_ROLES:
        return {}
    tid = getattr(user, "tenant_id", None)
    return {"tenantId": tid} if tid else {"tenantId": {"$exists": False}}


@router.get("")
async def get_alerts(_current_user: TokenData = Depends(get_current_user)):
    """Get alerts scoped to the caller's tenant."""
    db = get_database()
    alerts = await db.alerts.find(_tenant_filter(_current_user), {"_id": 0}).to_list(length=100)
    return alerts


_VALID_SEVERITIES: frozenset[str] = frozenset({"Critical", "High", "Medium", "Low", "Info", "critical", "high", "medium", "low", "info"})


@router.get("/search")
async def search_alerts(
    q: str = Query(..., min_length=1, description="Full-text search query"),
    severity: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    _current_user: TokenData = Depends(get_current_user),
):
    """Full-text search across alert description, type, and source fields."""
    q = q[:200]
    if severity and severity not in _VALID_SEVERITIES:
        raise HTTPException(status_code=400, detail=f"Invalid severity. Must be one of: {sorted(_VALID_SEVERITIES)}")
    db = get_database()
    tf = _tenant_filter(_current_user)
    alerts: list = []
    try:
        filt: dict[str, Any] = {"$text": {"$search": q}, **tf}
        if severity:
            filt["severity"] = severity
        alerts = await db.alerts.find(filt, {"_id": 0}).to_list(length=limit)
    except Exception as _e:
        logger.debug("Text index search unavailable, falling back to regex: %s", _e)

    if not alerts:
        import re as _re
        regex = {"$regex": _re.escape(q), "$options": "i"}
        filt_regex: dict[str, Any] = {
            "$or": [{"description": regex}, {"type": regex}, {"source.hostname": regex}],
            **tf,
        }
        if severity:
            filt_regex["severity"] = severity
        alerts = await db.alerts.find(filt_regex, {"_id": 0}).limit(1000).to_list(length=limit)
    return alerts


_VALID_ALERT_SEVERITIES = frozenset({"Critical", "High", "Medium", "Low", "Info"})
_VALID_ALERT_STATUSES = frozenset({"open", "acknowledged", "resolved", "false_positive"})


class AlertCreate(BaseModel):
    type: str = Field(..., max_length=100)
    severity: str = Field("Medium", max_length=20)
    title: str = Field(..., max_length=500)
    description: str = Field("", max_length=5000)
    source: Optional[dict] = None
    metadata: Optional[dict] = None

    model_config = {"extra": "forbid"}


@router.post("")
async def create_alert(
    alert_in: AlertCreate,
    _current_user: TokenData = Depends(get_current_user),
):
    """Create a new alert and broadcast it to real-time subscribers."""
    if alert_in.severity not in _VALID_ALERT_SEVERITIES:
        raise HTTPException(status_code=400, detail=f"severity must be one of: {sorted(_VALID_ALERT_SEVERITIES)}")
    db = get_database()
    now = datetime.now(timezone.utc).isoformat()
    alert = alert_in.model_dump()
    alert["id"] = str(uuid.uuid4())
    alert["timestamp"] = now
    alert["status"] = "open"
    user_tenant = getattr(_current_user, "tenant_id", None)
    if user_tenant:
        alert["tenantId"] = user_tenant
    await db.alerts.insert_one({**alert, "_id": alert["id"]})
    alert.pop("_id", None)

    # Broadcast to SSE/WebSocket subscribers so the UI updates in real time
    try:
        from streaming_service import broker
        tenant_id = alert.get("tenantId") or alert.get("tenant_id") or None
        if tenant_id:
            await broker.publish(f"alerts:{tenant_id}", alert)
    except Exception as _e:
        logger.warning("Failed to broadcast alert to streaming service: %s", _e)

    return alert


class AlertAssignRequest(BaseModel):
    assigned_to: str = Field(..., min_length=1, max_length=320)


@router.patch("/{alert_id}/assign")
async def assign_alert(
    alert_id: str,
    body: AlertAssignRequest,
    _current_user: TokenData = Depends(require_permission("manage:security_cases")),
):
    """Assign an alert to a specific user (tenant-scoped)."""
    assigned_to = body.assigned_to
    db = get_database()
    now = datetime.now(timezone.utc).isoformat()
    result = await db.alerts.update_one(
        {"id": alert_id, **_tenant_filter(_current_user)},
        {"$set": {"assigned_to": assigned_to, "assigned_at": now, "status": "assigned"}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"alert_id": alert_id, "assigned_to": assigned_to, "assigned_at": now}


@router.delete("/bulk")
async def bulk_delete_alerts(
    ids: List[str] = Body(..., description="List of alert IDs to delete (max 500)"),
    _current_user: TokenData = Depends(require_permission("manage:security_cases")),
):
    """Delete multiple alerts by ID (tenant-scoped)."""
    ids = ids[:500]
    if not ids:
        raise HTTPException(status_code=400, detail="No IDs provided")
    db = get_database()
    result = await db.alerts.delete_many({"id": {"$in": ids}, **_tenant_filter(_current_user)})
    return {"deleted": result.deleted_count}


@router.patch("/bulk")
async def bulk_update_alerts(
    updates: dict[str, Any] = Body(..., description='{"ids": [...], "patch": {...}}'),
    _current_user: TokenData = Depends(require_permission("manage:security_cases")),
):
    """Apply the same patch to multiple alerts (tenant-scoped)."""
    ids = updates.get("ids", [])[:500]
    patch = updates.get("patch", {})
    if not ids or not patch:
        raise HTTPException(status_code=400, detail="ids and patch are required")
    patch.pop("id", None)   # prevent overwriting primary key
    patch.pop("tenantId", None)  # prevent tenant hopping
    db = get_database()
    result = await db.alerts.update_many(
        {"id": {"$in": ids}, **_tenant_filter(_current_user)},
        {"$set": patch},
    )
    return {"matched": result.matched_count, "modified": result.modified_count}
