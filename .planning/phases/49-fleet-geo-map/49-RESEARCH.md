# Phase 49 — Fleet Geo Map — RESEARCH

Condensed, codebase-grounded research. All file:line refs verified against the tree on 2026-07-30.

## 1. Existing-surface audit (what already exists → what's genuinely new)

| Surface | State | Reuse / new |
|---------|-------|-------------|
| `components/GeographicAttackMap.tsx` | A **country bar-list + event table** (threat-origin heatmap), NOT a positioned SVG map. `view:geographic_map` / `geographicMap` AppView. | Do **not** reuse — different feature (security attacks). GMAP needs a real positioned map. |
| `components/NetworkTopologyMap.tsx` | Inline-SVG / data-URI icon rendering, `<svg>` canvas at `w-full h-[700px]`. | Convention reference for inline-SVG, air-gapped rendering. |
| `Agent` interface (types.ts:676) | Already carries `hostname`, `ipAddress` (LAN), `publicIp?`, `geo?` (`GeoLocation`), `status`, `tenantId`, `version`. | **All GMAP-03 drill-down fields already exist.** No new agent fields needed. |
| `GeoLocation` (types.ts:696) | `country`, `country_code`, `city`, `region`, `latitude?`, `longitude?`, `vpn_heuristic?`, `asn?`. | Marker positioning uses `latitude`/`longitude`; label uses `city`/`country`. |
| `utils/geo.ts` | `flagEmoji(code)`, `formatGeo({city,region,country})`. | Reuse for drill-down location label + flag. |
| `backend/agent_fleet_observability_endpoints.py` | 48-03 `GET /api/fleet/observability`, `APIRouter(prefix="/api/fleet")`, tenant-gated via `is_super_admin` + wrapped `get_database()`, `_PROJECTION` + `_project()`. | **Exact template** for the 49-01 `/api/fleet/geo` endpoint. |
| `backend/router_registry.py:281` | `_load(app, "agent_fleet_observability_endpoints", "router")`. | Add `_load(app, "agent_fleet_geo_endpoints", "router")` after it. |
| `components/icons.tsx:187` | `GlobeIcon`. | Sidebar entry icon. |
| App.tsx `fleetObservability` (166 lazy / 369 permission-map / 1915 switch) + Sidebar.tsx:417 | 48-05 4-file registration. | **Exact template** for 49-05 `fleetGeoMap` registration. |
| `services/apiService.ts:5033` `fetchFleetObservability` (`authFetch(`${API_BASE}/fleet/observability`)`) | 48-05 client. | Template for `fetchFleetGeo` → `/api/fleet/geo`. |

**Net:** Phase 49 is **frontend-primary**. Backend work is one thin projection endpoint. No new agent data model, no migration.

## 2. GMAP-01 — air-gapped basemap + projection

**Projection (equirectangular / Plate Carrée):** with an SVG `viewBox="0 0 360 180"` the projection is a direct linear map, no trig, no library:

```
x = lon + 180        // lon ∈ [-180,180] → x ∈ [0,360]
y = 90  - lat        // lat ∈ [ -90, 90] → y ∈ [0,180]   (north-up: subtract from 90)
```

Scale to any pixel width/height by `x_px = x/360 * W`, `y_px = y/180 * H`. Because the basemap SVG uses the same `viewBox`, markers layered in the same coordinate space line up with the land outline automatically.

**Basemap asset:** vendor a compact public-domain equirectangular world land-outline SVG (Natural Earth 1:110m is public domain) as an exported string in `components/worldMapAsset.ts`, rendered as the first child of the map `<svg viewBox="0 0 360 180">`. **Fallback (offline-safe, no asset):** an equirectangular graticule — `<line>` grid every 30° of lon/lat plus an equator/prime-meridian emphasis — is enough of a "map" backdrop to satisfy "renders fully with network blocked." 49-03 delivers the projection + backdrop; the land-outline string is the preferred fill, graticule the guaranteed floor.

**Air-gap verification:** the whole map is inline SVG + a bundled string. No `<img src=…>`, no `fetch` to any tile host, no CDN `<link>`/`<script>`. Verify by grepping the new files for `http`, `fetch(`, `tile`, `cdn` → none permitted (asserted in 49-04 must_haves prohibitions).

## 3. GMAP-02 — clustering + filters

**Clustering (D-04):** project every located agent to pixel `x/y`, bucket by fixed grid cell `key = (floor(x/CELL), floor(y/CELL))` (CELL ≈ 24–32 px). A cell with 1 agent renders a single status-colored marker; a cell with ≥2 renders one cluster marker showing the count, colored by worst-status in the cell (Error/Quarantined > Offline > Online). Zero distance math, zero deps. Extract to `utils/fleetClustering.ts` if `FleetGeoMap.tsx` nears 500 lines.

**Filters:** two controls — tenant (`<select>` populated from the distinct `tenantId`s in the payload; "All tenants" default) and status (multi-toggle over Online/Offline/Error/Quarantined). Filters apply **before** clustering so cluster counts reflect the filtered set. Unlocated agents (no lat/lon, D-07) are excluded from the map and shown as an "Unlocated (N)" chip that still respects the active filters.

## 4. GMAP-03 — drill-down

Clicking a single marker (or a cluster → expands to a small list, then a marker) opens a side panel reading only payload fields (D-06): `hostname`, LAN `ipAddress`, `publicIp`, resolved location via `formatGeo(geo)` + `flagEmoji(geo.country_code)`, and `status` (status-colored badge). No extra fetch.

## 5. Backend endpoint shape (49-01)

`GET /api/fleet/geo` — mirror 48-03 exactly:
- `APIRouter(prefix="/api/fleet", tags=["Fleet Geo Map"])`, route `/geo`.
- `current_user=Depends(get_current_user)`; `db = get_database()` (wrapped — never `db._db`).
- `query = {}`; if `not is_super_admin(role)`: `query["tenantId"] = current_user.tenant_id`.
- Projection returns per agent: `agentId(id)`, `hostname`, `status`, `tenantId`, `lanIp(ipAddress)`, `publicIp`, `geo{city,country,country_code,latitude,longitude}`.
- Response: `{ agents: [...], total, located_count, unlocated_count, tenants: [distinct tenantIds] }`.
- Fail-closed: an agent missing `geo`/coords is still returned (geo=null) and counted as unlocated (D-07).

**Test (TDD, mirror `test_agent_fleet_observability.py`):** hermetic, mocked async cursor, `dependency_overrides[get_current_user]`. Assert (a) super-admin sees cross-tenant agents; (b) non-super-admin query is tenant-scoped; (c) located vs unlocated counting; (d) projection carries the drill-down fields.

## 6. Deps & risk

- **No new npm deps.** No new pip deps.
- **Only real risk:** sourcing the public-domain world-outline SVG offline. Mitigated by the graticule fallback — the phase never blocks on the asset.
- **RBAC risk:** cross-tenant leak if `db._db` used — pinned by D-02 + test (b).
