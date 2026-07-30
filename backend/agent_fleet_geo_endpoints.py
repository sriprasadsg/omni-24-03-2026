"""
Agent Fleet Geo Map Endpoints — Phase 49 (GMAP-02/03)

GET /api/fleet/geo — one admin-facing cross-tenant aggregate of the fleet's
agents with only the fields the map needs: identity (id/hostname), status,
tenantId, LAN IP (`ipAddress`) + public IP (`publicIp`), and the resolved geo
(city/country/country_code + latitude/longitude). The client does all
clustering + filtering; this endpoint does RBAC + tenant scoping + projection.

Tenant gating clones `agent_fleet_observability_endpoints` verbatim: a
non-super-admin only ever sees their own tenant's agents (query gains a
tenantId filter); a super-admin sees the full fleet. Always reads the
request-scoped wrapped `db` from `get_database()` — NEVER `db._db` (T-48-07:
raw access here would leak cross-tenant agents).

Agents whose geo lacks numeric latitude AND longitude are still returned
(geo=null) and counted as unlocated — never silently dropped (D-07).
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends

from authentication_service import get_current_user
from database import get_database
from rbac_utils import is_super_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/fleet", tags=["Fleet Geo Map"])

_PROJECTION = {
    "_id": 0, "id": 1, "hostname": 1, "status": 1, "tenantId": 1,
    "ipAddress": 1, "publicIp": 1, "geo": 1,
}


def _geo(g: Any) -> Optional[Dict[str, Any]]:
    """Return the map-relevant geo subset, or None when not positionable.

    Requires numeric latitude AND longitude; a missing/partial/non-numeric
    coordinate pair is treated as unlocated (D-07).
    """
    if not isinstance(g, dict):
        return None
    lat = g.get("latitude")
    lon = g.get("longitude")
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return None
    return {
        "city": g.get("city"),
        "country": g.get("country"),
        "country_code": g.get("country_code"),
        "latitude": lat,
        "longitude": lon,
    }


def _project(agent: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": agent.get("id"),
        "hostname": agent.get("hostname"),
        "status": agent.get("status"),
        "tenantId": agent.get("tenantId"),
        "lanIp": agent.get("ipAddress"),
        "publicIp": agent.get("publicIp"),
        "geo": _geo(agent.get("geo")),
    }


@router.get("/geo")
async def get_fleet_geo(current_user=Depends(get_current_user)):
    """
    Return the fleet's agents with map-relevant fields.

    Super-admin sees every tenant's agents; a non-super-admin is scoped to
    their own tenantId. Located agents carry a geo{lat,lon,...}; unlocated
    agents carry geo=null and are counted separately (never dropped).
    """
    db = get_database()

    query: Dict[str, Any] = {}
    if not is_super_admin(getattr(current_user, "role", None)):
        query["tenantId"] = getattr(current_user, "tenant_id", None)

    agents: List[Dict[str, Any]] = await db.agents.find(query, _PROJECTION).to_list(length=None)

    projected = [_project(a) for a in agents]
    located = [a for a in projected if a["geo"] is not None]

    return {
        "agents": projected,
        "total": len(projected),
        "located_count": len(located),
        "unlocated_count": len(projected) - len(located),
        "tenants": sorted({a["tenantId"] for a in projected if a.get("tenantId")}),
    }
