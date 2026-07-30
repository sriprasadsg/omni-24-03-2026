# 49-01 SUMMARY — Fleet Geo backend endpoint (GMAP-02/03)

**Status:** Done. Commits `d8f26e6` (test), `01ec97b` (impl).

## Delivered
- NEW `backend/agent_fleet_geo_endpoints.py` — `GET /api/fleet/geo`, `APIRouter(prefix="/api/fleet", tags=["Fleet Geo Map"])`. Clones 48-03 tenant gating: `is_super_admin(role)` → whole fleet, else `query["tenantId"]` scoped. Reads wrapped `get_database()` (never `db._db`, T-48-07). Projects `{id, hostname, status, tenantId, lanIp(ipAddress), publicIp, geo{city,country,country_code,latitude,longitude}|null}`. Response adds `total, located_count, unlocated_count, tenants[]`. Unlocated agents (missing/partial numeric coords) returned with `geo=null`, counted separately (D-07).
- EDIT `backend/router_registry.py` — `_load(app, "agent_fleet_geo_endpoints", "router")` after the fleet-observability load.
- NEW `backend/tests/test_agent_fleet_geo.py` — 5 hermetic tests (super-admin cross-tenant, non-super-admin tenant-scoped, located/unlocated counting, drill-down projection, partial-coords→unlocated).

## Verification
- `pytest backend/tests/test_agent_fleet_geo.py` → **5 passed** (red before impl confirmed).
- `router_registry` import smoke OK; route `/api/fleet/geo` registered.
- Full `tests/`: 1446 passed / 6 pre-existing fails (none from this plan).

## Deviations
None.
