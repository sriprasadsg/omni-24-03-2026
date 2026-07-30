# Phase 49 — Fleet Geo Map — CONTEXT

**Milestone:** v3.3 (Agent Geo & Fleet Observability) — final phase (46→47→48→**49**)
**Requirements:** GMAP-01, GMAP-02, GMAP-03
**Depends on:** Phase 46 (per-agent geo/lat-lon enrichment on the `Agent` payload), Phase 47 (status/VPN flags surfaced on drill-down), Phase 48 (offline/status semantics feeding the status filter)

## Goal

Give admins one visual, air-gapped-safe map of where their fleet physically is, with clustering and drill-down — reading data that already exists on the `Agent` record. Highest-visibility surface in the milestone, built last because it reads everything upstream.

## Success criteria (what must be TRUE)

1. An admin can open a fleet map showing agent markers positioned by city/country; the map renders fully with outbound network blocked — no tile-server dependency (GMAP-01).
2. Dense clusters of nearby agents collapse into a single cluster marker with a count; the admin can filter by tenant and by agent status (online/offline/error/quarantined) (GMAP-02).
3. Clicking a marker drills into that agent — hostname, LAN IP, public IP, resolved location, current status (GMAP-03).

## Locked decisions

- **D-01 — Air-gapped basemap + projection (GMAP-01).** Basemap is a vendored, self-contained world-outline SVG stored as an exported string module (`components/worldMapAsset.ts`), rendered with `viewBox="0 0 360 180"` so the equirectangular projection is a direct linear map: `x = lon + 180`, `y = 90 - lat`. Projection helper lives in `utils/worldMap.ts`. **No** map/charting npm dependency (d3-geo, topojson, leaflet, react-simple-maps) and **no** external tile/CDN request — matches the repo's inline-SVG convention (`NetworkTopologyMap.tsx`).
  - *Basemap sourcing:* vendor a compact (<80 KB) **public-domain** equirectangular world-outline SVG (Natural Earth 1:110m land is public domain). **Fallback if none is bundleable offline:** render an equirectangular graticule (grid lines every 30°) as the backdrop — still air-gapped, still "a map." This is the phase's one asset dependency; flagged in 49-03.
- **D-02 — Data source: new admin-gated `GET /api/fleet/geo` (GMAP-02/03).** A thin cross-tenant aggregate endpoint that **clones the 48-03 `agent_fleet_observability_endpoints` tenant gating verbatim**: super-admin sees the whole fleet; a non-super-admin sees only their own `tenantId`. Returns only map-relevant projected fields. The client does clustering + filtering; the server does RBAC + tenant scoping. Registered via `router_registry._load`.
- **D-03 — Nav registration clones the 48-05 4-file pattern.** New `AppView` member `fleetGeoMap` (types.ts) + App.tsx lazy import / permission map / switch case + Sidebar entry, gated by `manage:agents`, using the existing `GlobeIcon`. **Distinct** from the pre-existing `geographicMap` / `GeographicAttackMap` (the *security attack* heatmap) — do not reuse or modify it.
- **D-04 — Clustering: client-side pixel-grid buckets (GMAP-02).** Collapse markers whose projected positions fall in the same fixed pixel-grid cell into one cluster marker with a count badge. No clustering library, no server-side clustering, no great-circle distance math — grid buckets on projected `x/y`.
- **D-05 — Marker color reuses the existing agent-status color convention** (from `AgentList.tsx`): Online / Offline / Error / Quarantined. Do not invent a new status palette.
- **D-06 — Drill-down reads only the `/api/fleet/geo` payload** (hostname, LAN `ipAddress`, `publicIp`, resolved `geo`, `status`). No extra per-agent fetch on marker click.
- **D-07 — Unlocated agents are surfaced, not dropped.** Agents with no `latitude`/`longitude` are returned by the endpoint and rendered as an off-map "Unlocated (N)" count — never silently discarded (GMAP-01 honesty).

## Scope fences (MUST NOT)

- MUST NOT add any map/charting npm dependency (d3-geo, topojson-client, leaflet, react-simple-maps, maplibre).
- MUST NOT make any external network / tile / CDN request (air-gap; CSP-safe, self-contained assets only).
- MUST NOT reuse, rename, or modify the existing `geographicMap` / `GeographicAttackMap` (separate security-attack feature) or the `view:geographic_map` permission.
- MUST NOT re-derive offline/version/status logic on the client — render the server-reported `status`.
- MUST NOT access `db._db` in the endpoint — use the request-scoped wrapped `get_database()` + `is_super_admin` gate (cross-tenant-leak pitfall, below).

## Pitfalls (carried from Phase 48)

- **T-48-07 (cross-tenant leak):** raw `db._db` access in a fleet handler bypasses the request-scoped tenant wrapper and leaks other tenants' agents. The 48-03 endpoint reads the wrapped `db` from `get_database()` and applies `is_super_admin(role)` → full fleet else `tenantId` filter. Clone that exactly.
- **500-line file rule:** the vendored world-outline SVG string can be large. Keep it in its own module (`components/worldMapAsset.ts`); the projection in `utils/worldMap.ts`; `FleetGeoMap.tsx` stays lean (extract cluster math to `utils/fleetClustering.ts` if the component approaches 500 lines).

## Plan breakdown

| Plan | Wave | Scope | Requirements |
|------|------|-------|--------------|
| 49-01 | 1 | Backend `GET /api/fleet/geo` cross-tenant aggregate + registry + failing-test-first | GMAP-02/03 (data) |
| 49-02 | 1 | Frontend contract: `FleetGeoAgent`/`FleetGeoResponse` types + `fleetGeoMap` AppView + `fetchFleetGeo` client | GMAP-01/02/03 (contract) |
| 49-03 | 1 | Air-gapped basemap asset (`worldMapAsset.ts`) + equirectangular projection (`utils/worldMap.ts`) | GMAP-01 |
| 49-04 | 2 | `FleetGeoMap.tsx` — basemap + status-colored markers + grid clustering + tenant/status filters + drill-down panel | GMAP-01/02/03 |
| 49-05 | 3 | Nav registration (App.tsx + Sidebar), clone of 48-05 4-file pattern, `manage:agents` + `GlobeIcon` | GMAP-01 (reachability) |
