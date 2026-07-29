"""Agent location history endpoints.

Serves two URL spaces:
  - GET /api/agents/{agent_id}/location-history (GAUD-02)
  - GET/PATCH /api/settings/agent-location-tracking (D-02)

No PATCH/DELETE/PUT route exists for the location-history resource. That absence
is GAUD-01's immutability enforcement — the agent_location_history
collection is append-only, written exclusively by
agent_location_history_service.record_location_change.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from database import get_database
from authentication_service import get_current_user
from agent_location_history_service import get_track_agent_location
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

router = APIRouter()

# Admin roles for settings-mutation gating
_SETTINGS_ADMIN_ROLES = {"Super Admin", "super_admin", "admin", "platform-admin", "Tenant Admin"}


def _require_admin(user) -> None:
    """Raise 403 if the caller does not have an admin role."""
    if getattr(user, "role", "") not in _SETTINGS_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin role required to modify settings")


class AgentLocationTrackingUpdate(BaseModel):
    enabled: bool

# ---------------------------------------------------------------------------
# GET /api/agents/{agent_id}/location-history  (GAUD-02)
# ---------------------------------------------------------------------------

@router.get("/api/agents/{agent_id}/location-history")
async def get_agent_location_history(
    agent_id: str,
    current_user=Depends(get_current_user),
):
    """Return the append-only location history for an agent."""
    try:
        db = get_database()
        raw = db._db if hasattr(db, "_db") else db
        tenant_id = getattr(current_user, "tenant_id", None)

        # agent_location_history rows are written with the "agent_id" key
        # (see agent_location_history_service.py._promote) — never "agentId".
        query: dict = {"agent_id": agent_id}
        if tenant_id:
            query["tenantId"] = tenant_id

        entries = await raw.agent_location_history.find(
            query, {"_id": 0}
        ).sort("timestamp", 1).to_list(length=500)

        # Belt-and-braces (T-46-04-A / Pitfall 3): re-check tenantId in
        # application code too, never trusting the query filter alone.
        if tenant_id:
            entries = [e for e in entries if e.get("tenantId") == tenant_id]

        # Dwell time computed at read time (Pitfall 2) — never a stored
        # field. For ascending row i: dwell_seconds = timestamp(i+1) -
        # timestamp(i); the last (most recent) row uses now - timestamp(last),
        # since that agent may still be at that location.
        now = datetime.now(timezone.utc)
        for i, entry in enumerate(entries):
            if i + 1 < len(entries):
                delta = entries[i + 1]["timestamp"] - entry["timestamp"]
            else:
                delta = now - entry["timestamp"]
            entry["dwell_seconds"] = delta.total_seconds()

        return {"agent_id": agent_id, "entries": entries}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_agent_location_history error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# GET/PATCH /api/settings/agent-location-tracking (D-02)
# ---------------------------------------------------------------------------

@router.get("/api/settings/agent-location-tracking")
async def get_agent_location_tracking_settings(current_user=Depends(get_current_user)):
    try:
        db = get_database()
        tenant_id = getattr(current_user, "tenant_id", None)
        enabled = await get_track_agent_location(db, tenant_id)
        return {"enabled": enabled}
    except Exception as e:
        logger.error("get_agent_location_tracking_settings error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/api/settings/agent-location-tracking")
async def patch_agent_location_tracking_settings(body: AgentLocationTrackingUpdate, current_user=Depends(get_current_user)):
    try:
        _require_admin(current_user)
        db = get_database()
        raw = db._db if hasattr(db, "_db") else db
        tenant_id = getattr(current_user, "tenant_id", None)
        doc = {"type": "track_agent_location", "enabled": body.enabled}

        if tenant_id:
            doc["tenantId"] = tenant_id
            await raw.system_settings.update_one(
                {"type": "track_agent_location", "tenantId": tenant_id},
                {"$set": doc}, upsert=True,
            )
        else: # Global setting
            await raw.system_settings.update_one(
                {"type": "track_agent_location", "tenantId": {"$exists": False}},
                {"$set": doc}, upsert=True,
            )
        return {"enabled": body.enabled}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("patch_agent_location_tracking_settings error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
