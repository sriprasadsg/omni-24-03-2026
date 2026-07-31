"""
Agent Uptime Endpoints — Phase 48 (FOBS-02)

GET /api/agents/{agent_id}/uptime?hours=N — on-the-fly heartbeat-presence
uptime % + bucketed timeline, computed from the `agent_metrics` collection
(NEVER `agent_metrics_history`, a capped decoy — see agent_uptime_service.py
module docstring and 48-RESEARCH.md D-09).

Tenant gating (V4 access control) is cloned verbatim from
`agent_metrics_endpoints.get_agent_metrics_history`: a non-super-admin only
sees uptime for agents within their own tenant; agents outside scope 404
rather than leak existence (T-48-01). `hours` is clamped to 1..48 server-side
(V5 input validation / D-02 / T-48-02) before any query is issued.
"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from agent_uptime_service import compute_uptime
from authentication_service import get_current_user
from database import get_database

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agents", tags=["Agent Uptime"])

# Matches agent_metrics_endpoints._METRICS_SUPER_ROLES exactly, for
# consistency with the endpoint whose tenant-gating shape this reproduces.
_UPTIME_SUPER_ROLES = {"Super Admin", "super_admin", "platform-admin"}


@router.get("/{agent_id}/uptime")
async def get_agent_uptime(
    agent_id: str,
    hours: int = 24,
    current_user=Depends(get_current_user),
):
    """
    Return heartbeat-presence uptime % + bucketed timeline for an agent over
    the last `hours` hours (clamped to 1..48 — D-02 locks the exposed range
    to this phase's UI presets; no larger windows).
    """
    hours = max(1, min(hours, 48))

    # Request-scoped wrapped db handle — NEVER db._db in this handler
    # (Pitfall 5 / T-48-01: raw access here would leak cross-tenant rows).
    db = get_database()
    user_role = getattr(current_user, "role", "")
    tenant_id = getattr(current_user, "tenant_id", None) or getattr(current_user, "tenantId", None)

    agent_filter: dict = {"id": agent_id}
    if user_role not in _UPTIME_SUPER_ROLES and tenant_id:
        agent_filter["tenantId"] = tenant_id
    agent = await db.agents.find_one(agent_filter, {"_id": 0, "tenantId": 1})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    metrics_filter: dict = {"agent_id": agent_id, "timestamp": {"$gte": since}}
    if user_role not in _UPTIME_SUPER_ROLES and tenant_id:
        metrics_filter["tenant_id"] = tenant_id
    rows = await db.agent_metrics.find(
        metrics_filter, {"_id": 0, "timestamp": 1}
    ).sort("timestamp", 1).to_list(length=5760)  # 48h ceiling at 30s cadence = 5760 buckets

    result = compute_uptime(rows, hours)
    return {"agent_id": agent_id, "hours": hours, **result}
