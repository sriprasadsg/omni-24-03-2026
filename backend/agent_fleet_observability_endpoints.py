"""
Agent Fleet Observability Endpoints — Phase 48 (FOBS-03)

GET /api/fleet/observability — one admin-gated aggregate view of the fleet's
offline agents (reusing the existing `status == "Offline"` set maintained by
`app_background_tasks.monitor_agent_status()`) and its version-drift list
(each agent's reported version vs the single global `_LATEST_AGENT_VERSION`,
compared via the existing `agent_auto_update_service._parse_ver` — never a
new parser or a new offline heuristic; D-03 / Don't Hand-Roll).

Tenant gating (V4 access control) clones `agent_core_endpoints.get_agents`'s
shape verbatim: a non-super-admin only ever sees their own tenant's agents
(query gains a tenantId filter); a super-admin sees the full fleet. Always
reads through the request-scoped wrapped `db` from `get_database()` — NEVER
`db._db` in this handler (Pitfall 5 / T-48-07: raw access here would leak
cross-tenant agents).
"""
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends

from agent_auto_update_service import _LATEST_AGENT_VERSION, _parse_ver
from authentication_service import get_current_user
from database import get_database
from rbac_utils import is_super_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/fleet", tags=["Fleet Observability"])

_PROJECTION = {"_id": 0, "id": 1, "hostname": 1, "status": 1, "version": 1, "tenantId": 1}


def _project(agent: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": agent.get("id"),
        "hostname": agent.get("hostname"),
        "status": agent.get("status"),
        "version": agent.get("version"),
        "tenantId": agent.get("tenantId"),
    }


@router.get("/observability")
async def get_fleet_observability(current_user=Depends(get_current_user)):
    """
    Return the fleet's offline agents + version-drift list.

    offline_agents: agents with status == "Offline" (the set
    monitor_agent_status() maintains — not a new freshness heuristic).
    version_drift: agents whose reported version parses (_parse_ver) and is
    strictly older than _LATEST_AGENT_VERSION. A malformed or missing
    reported version is fail-closed excluded (never raises).
    """
    db = get_database()

    query: Dict[str, Any] = {}
    if not is_super_admin(getattr(current_user, "role", None)):
        query["tenantId"] = getattr(current_user, "tenant_id", None)

    agents: List[Dict[str, Any]] = await db.agents.find(query, _PROJECTION).to_list(length=None)

    latest_parsed = _parse_ver(_LATEST_AGENT_VERSION)

    offline_agents = [_project(a) for a in agents if a.get("status") == "Offline"]

    version_drift = []
    for agent in agents:
        parsed = _parse_ver(agent.get("version"))
        if parsed is not None and latest_parsed is not None and parsed < latest_parsed:
            version_drift.append(_project(agent))

    return {
        "latest_version": _LATEST_AGENT_VERSION,
        "offline_agents": offline_agents,
        "offline_count": len(offline_agents),
        "version_drift": version_drift,
        "drift_count": len(version_drift),
    }
