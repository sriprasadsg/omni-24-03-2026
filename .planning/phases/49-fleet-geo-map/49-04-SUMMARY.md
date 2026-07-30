# 49-04 SUMMARY — FleetGeoMap component (GMAP-01/02/03)

**Status:** Done. Commit `dd81d4f`.

## Delivered
- NEW `utils/fleetClustering.ts` — `clusterAgents(agents, cellPx, width, height): GeoCluster[]`. Projects located agents, grid-buckets by `floor(x/cell):floor(y/cell)`, emits one cluster per cell at the members' mean position with `count` + `worstStatus` (Quarantined > Error > Offline > Online). Ignores unlocated agents. Deterministic top-left→bottom-right ordering.
- NEW `components/FleetGeoMap.tsx` (264 lines) — named export `FleetGeoMap`. Fetches `/api/fleet/geo` (loading/error states cloned from FleetObservabilityDashboard). Renders `<svg viewBox="0 0 360 180">` with `WORLD_BACKDROP_SVG` layer + status-colored markers/clusters (count badge on collapsed cells). Tenant `<select>` (from `response.tenants`) + status multi-toggle, applied **before** clustering. Marker click → drill-down panel (hostname, LAN IP, public IP, location via `flagEmoji`+`formatGeo`, status badge); multi-agent cluster click → expandable agent list. Unlocated agents shown as an "Unlocated (N)" chip (D-07). Status palette replicates AgentList `statusInfo` (D-05).
- NEW `src/__tests__/fleetClustering.test.ts` — 6 vitest cases (collapse, split, worst-status, empty, unlocated-ignored, single-cluster positioning).

## Verification
- `npx tsc --noEmit` — clean for touched files; `npm run build` clean.
- `npx vitest run src/__tests__/fleetClustering.test.ts` → **6 passed**.
- Air-gap grep over `FleetGeoMap.tsx` → clean (only data call is `fetchFleetGeo` via authFetch). File 264 lines (< 500).

## Deviations
- Backdrop injected via `dangerouslySetInnerHTML` on a `<g>` — source is the bundled `WORLD_BACKDROP_SVG` constant, never user/network data (documented; T-49-05). Clustering done in the native 360×180 viewBox space (CSS-scaled), so marker/cluster alignment is resolution-independent.
