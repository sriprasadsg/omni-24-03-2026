# 49-02 SUMMARY — Fleet Geo frontend contract (GMAP-01/02/03)

**Status:** Done. Commit `f934375`.

## Delivered
- EDIT `services/apiService.ts` — `FleetGeoAgent` + `FleetGeoResponse` interfaces and `fetchFleetGeo(): Promise<FleetGeoResponse>` → `authFetch(`${API_BASE}/fleet/geo`)` with the standard error shape.
- EDIT `types.ts` — `| 'fleetGeoMap'` added to the `AppView` union (distinct from the pre-existing security-attack `geographicMap`).
- EDIT `App.tsx` — `fleetGeoMap: 'manage:agents'` in `viewPermissionMap`.

## Deviations (intentional)
- DTOs co-located in `apiService.ts`, **not `types.ts`** as the plan stated — matches the established `FleetObservability`/`FleetObservabilityAgent` precedent (defined in apiService.ts), keeping the fleet DTO convention consistent.
- The `viewPermissionMap` entry (planned for 49-05) landed **here** because `Record<AppView, Permission>` is exhaustive: adding the AppView member without the permission entry breaks strict `tsc`. 49-05 then only added the lazy import + switch case + Sidebar entry.

## Verification
- `npx tsc --noEmit` — no errors in touched files (remaining errors are pre-existing `servers/src` + `github-mcp-server/ui` subprojects, missing deps).
- `npm run build` clean.
