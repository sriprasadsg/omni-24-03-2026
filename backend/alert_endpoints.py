from fastapi import APIRouter, Depends, HTTPException, Body, Query
from typing import List, Any
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData
from rbac_utils import require_permission
from datetime import datetime, timezone
import uuid

router = APIRouter(prefix="/api/alerts", tags=["Alerts"])


@router.get("")
async def get_alerts(_current_user: TokenData = Depends(get_current_user)):
    """Get all alerts"""
    db = get_database()
    alerts = await db.alerts.find({}, {"_id": 0}).to_list(length=100)
    return alerts


@router.get("/search")
async def search_alerts(
    q: str = Query(..., min_length=1, description="Full-text search query"),
    severity: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    _current_user: TokenData = Depends(get_current_user),
):
    """Full-text search across alert description, type, and source fields."""
    db = get_database()
    alerts: list = []
    try:
        filt: dict[str, Any] = {"$text": {"$search": q}}
        if severity:
            filt["severity"] = severity
        alerts = await db.alerts.find(filt, {"_id": 0}).to_list(length=limit)
    except Exception:
        pass  # No text index — fall through to regex

    if not alerts:
        regex = {"$regex": q, "$options": "i"}
        filt_regex: dict[str, Any] = {
            "$or": [{"description": regex}, {"type": regex}, {"source.hostname": regex}]
        }
        if severity:
            filt_regex["severity"] = severity
        alerts = await db.alerts.find(filt_regex, {"_id": 0}).to_list(length=limit)
    return alerts


@router.post("")
async def create_alert(
    alert: dict = Body(...),
    _current_user: TokenData = Depends(get_current_user),
):
    """Create a new alert and broadcast it to real-time subscribers."""
    db = get_database()
    now = datetime.now(timezone.utc).isoformat()
    alert.setdefault("id", str(uuid.uuid4()))
    alert.setdefault("timestamp", now)
    alert.setdefault("status", "open")
    await db.alerts.insert_one({**alert, "_id": alert["id"]})
    alert.pop("_id", None)

    # Broadcast to SSE/WebSocket subscribers so the UI updates in real time
    try:
        from streaming_service import broker
        tenant_id = alert.get("tenantId") or alert.get("tenant_id", "default")
        await broker.publish(f"alerts:{tenant_id}", alert)
    except Exception:
        pass  # Streaming service unavailable — alert is still persisted

    return alert


@router.patch("/{alert_id}/assign")
async def assign_alert(
    alert_id: str,
    body: dict = Body(..., example={"assigned_to": "analyst@corp.com"}),
    _current_user: dict = Depends(require_permission("manage:security_cases")),
):
    """Assign an alert to a specific user."""
    assigned_to = body.get("assigned_to")
    if not assigned_to:
        raise HTTPException(status_code=400, detail="assigned_to is required")
    db = get_database()
    now = datetime.now(timezone.utc).isoformat()
    result = await db.alerts.update_one(
        {"id": alert_id},
        {"$set": {"assigned_to": assigned_to, "assigned_at": now, "status": "assigned"}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"alert_id": alert_id, "assigned_to": assigned_to, "assigned_at": now}


@router.delete("/bulk")
async def bulk_delete_alerts(
    ids: List[str] = Body(..., description="List of alert IDs to delete"),
    _current_user: dict = Depends(require_permission("manage:security_cases")),
):
    """Delete multiple alerts by ID."""
    if not ids:
        raise HTTPException(status_code=400, detail="No IDs provided")
    db = get_database()
    result = await db.alerts.delete_many({"id": {"$in": ids}})
    return {"deleted": result.deleted_count}


@router.patch("/bulk")
async def bulk_update_alerts(
    updates: dict[str, Any] = Body(..., description='{"ids": [...], "patch": {...}}'),
    _current_user: dict = Depends(require_permission("manage:security_cases")),
):
    """Apply the same patch to multiple alerts."""
    ids = updates.get("ids", [])
    patch = updates.get("patch", {})
    if not ids or not patch:
        raise HTTPException(status_code=400, detail="ids and patch are required")
    patch.pop("id", None)  # prevent overwriting primary key
    db = get_database()
    result = await db.alerts.update_many({"id": {"$in": ids}}, {"$set": patch})
    return {"matched": result.matched_count, "modified": result.modified_count}
