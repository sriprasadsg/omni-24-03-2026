# 49-05 SUMMARY — Fleet Geo Map nav registration (GMAP-01)

**Status:** Done. Commit `2221900`.

## Delivered
- EDIT `App.tsx` — `const FleetGeoMap = lazy(() => import('./components/FleetGeoMap')…)`; `case 'fleetGeoMap': return <ErrorBoundary name="FleetGeoMap"><FleetGeoMap /></ErrorBoundary>;`.
- EDIT `components/Sidebar.tsx` — nav entry `{ view: 'fleetGeoMap', label: 'Fleet Geo Map', icon: <GlobeIcon size={20} />, permission: 'manage:agents' }` next to `fleetObservability`; `GlobeIcon` added to the `./icons` import.

## Note
The `viewPermissionMap` entry (`fleetGeoMap: 'manage:agents'`) landed in 49-02 (exhaustive-Record type requirement), so this plan is the remaining lazy-import + switch-case + Sidebar wiring. The existing `geographicMap` entry is untouched (D-03).

## Verification
- `npx tsc --noEmit` clean for `App.tsx`/`Sidebar.tsx`; `npm run build` clean.
- Build emits `FleetGeoMap-*.js` as its own lazy chunk → confirms the lazy import is wired.

## Pending human UAT
As `manage:agents` admin: sidebar "Fleet Geo Map" entry appears and opens the map (backdrop renders offline, markers/clusters, tenant/status filters, marker drill-down). As a non-`manage:agents` user: entry hidden and view unreachable.
