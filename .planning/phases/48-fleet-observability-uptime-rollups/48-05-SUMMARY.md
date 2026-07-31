---
phase: 48-fleet-observability-uptime-rollups
plan: 05
subsystem: ui
tags: [react, typescript, vite, admin-nav, fleet, observability, version-drift]

# Dependency graph
requires:
  - phase: 48-03
    provides: "GET /api/fleet/observability — fleet-wide offline_agents + version_drift aggregate"
provides:
  - "FleetObservabilityDashboard.tsx — admin-gated fleet-wide offline + version-drift renderer"
  - "fetchFleetObservability() apiService client"
  - "fleetObservability AppView + manage:agents-gated nav registration"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Cloned the Phase 47 SecuritySettingsDashboard 4-file admin-nav registration (types.ts AppView union + App.tsx lazy import/permission map/switch case + Sidebar.tsx entry) verbatim, swapping view key and permission"
    - "FleetObservabilityDashboard is a pure renderer over the 48-03 aggregate endpoint — no client-side offline/version-drift recomputation"

key-files:
  created:
    - components/FleetObservabilityDashboard.tsx
  modified:
    - services/apiService.ts
    - types.ts
    - App.tsx
    - components/Sidebar.tsx

key-decisions:
  - "Reused the API_BASE ('/api') + authFetch convention exactly as getGeoSecuritySettings does, throwing Error(err.detail) on non-ok responses rather than returning defaults, since a fleet-wide admin view should surface a load failure rather than silently show an empty fleet"
  - "AgentRow renders 'unknown' for a null/missing version field rather than omitting the row — matches the endpoint's fail-closed exclusion (malformed/missing versions never appear in version_drift, so any row shown always has a real drift comparison; 'unknown' only appears if a future backend change relaxes that guarantee)"

requirements-completed: [FOBS-03]

coverage:
  - id: D1
    description: "New admin-gated 'Fleet Observability' nav page reachable from the sidebar, registered across types.ts/App.tsx/Sidebar.tsx cloning the Phase 47 pattern"
    requirement: "FOBS-03"
    verification:
      - kind: other
        ref: "npx tsc --noEmit (clean) && npm run build (succeeds, FleetObservabilityDashboard-*.js chunk emitted)"
        status: pass
    human_judgment: true
    rationale: "Sidebar visibility and reachability for manage:agents holders (and hiddenness for others) is a UI/permission behavior best confirmed by a human clicking through the app, per the plan's own human-check verification step."
  - id: D2
    description: "Page lists offline agents and version-drifted agents sourced from GET /api/fleet/observability, with no client-side offline/version-drift logic"
    requirement: "FOBS-03"
    verification:
      - kind: other
        ref: "Manual code review: FleetObservabilityDashboard.tsx renders offline_agents/version_drift arrays verbatim from fetchFleetObservability(), computes nothing offline/version-related client-side"
        status: pass
    human_judgment: true
    rationale: "Confirming the rendered lists match live endpoint data (empty/loading/error states, real agent rows) requires visual/functional human verification against a running backend."
  - id: D3
    description: "Nav entry + view gated exclusively by manage:agents (D-07); users without it cannot see or reach the page"
    requirement: "FOBS-03"
    verification:
      - kind: other
        ref: "Manual code review: Sidebar.tsx entry permission: 'manage:agents', App.tsx viewPermissionMap fleetObservability: 'manage:agents' — no other permission referenced"
        status: pass
    human_judgment: true
    rationale: "Verifying the permission gate actually hides the entry and blocks the route for a non-admin session requires logging in as both an admin and non-admin user."

# Metrics
duration: 20min
completed: 2026-07-29
status: complete
---

# Phase 48 Plan 05: Fleet Observability Nav Page Summary

**Admin-gated "Fleet Observability" nav page (offline agents + version-drift lists) cloning the Phase 47 SecuritySettingsDashboard registration pattern, gated by manage:agents, rendering the 48-03 aggregate endpoint verbatim with no client-side offline/version logic.**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-07-29
- **Tasks:** 2/2 completed
- **Files modified:** 5 (1 created, 4 edited)

## Accomplishments

- `services/apiService.ts` — new `fetchFleetObservability()` calling `GET ${API_BASE}/fleet/observability`, mirroring `getGeoSecuritySettings`'s `authFetch` + error-shape convention. Added the `FleetObservability`/`FleetObservabilityAgent` TypeScript interfaces matching the 48-03 endpoint's exact response shape (`latest_version`, `offline_agents`, `offline_count`, `version_drift`, `drift_count`, each agent projected to `id/hostname/status/version/tenantId`).
- `components/FleetObservabilityDashboard.tsx` (new, named export `FleetObservabilityDashboard` matching the lazy-import shape App.tsx expects) — clones `SecuritySettingsDashboard`'s dark dashboard shell/styling. Fetches on mount, renders two sections ("Offline Agents", "Version Drift") each with a count badge, friendly empty state ("No offline agents" / "All agents on the latest version"), loading state, and an error state (with toast). Renders exactly the fields the endpoint returns — no client-side offline-detection or version-compare logic (D-03, T-48-14 accept disposition upheld).
- 4-file admin-nav registration, cloning the Phase 47 Security-panel pattern exactly (view key `geoSecurity`→`fleetObservability`, permission `manage:settings`→`manage:agents` per D-07):
  - `types.ts` — added `| 'fleetObservability'` to the `AppView` union.
  - `App.tsx` — lazy import (`import('./components/FleetObservabilityDashboard').then(m => ({ default: m.FleetObservabilityDashboard }))`), `fleetObservability: 'manage:agents'` in the permission map, and `case 'fleetObservability': return <ErrorBoundary name="FleetObservabilityDashboard"><FleetObservabilityDashboard /></ErrorBoundary>;` in the render switch.
  - `components/Sidebar.tsx` — new nav entry `{ view: 'fleetObservability', label: 'Fleet Observability', icon: <ActivityIcon size={20} />, permission: 'manage:agents' }`, placed alongside the `geoSecurity` row; reused the already-imported `ActivityIcon`.

## Task Commits

Each task was committed atomically:

1. **Task 1: fetchFleetObservability + FleetObservabilityDashboard component** - `0f2a23b` (feat)
2. **Task 2: 4-file admin-gated nav registration** - `726fa39` (feat)

**Plan metadata:** (pending — this commit)

## Files Created/Modified

- `components/FleetObservabilityDashboard.tsx` - new admin-gated fleet observability page (offline + version-drift renderer)
- `services/apiService.ts` - `fetchFleetObservability()` + `FleetObservability`/`FleetObservabilityAgent` types
- `types.ts` - `AppView` union gains `'fleetObservability'`
- `App.tsx` - lazy import, `manage:agents` permission-map entry, render switch case
- `components/Sidebar.tsx` - nav entry gated by `manage:agents`

## Decisions Made

- `fetchFleetObservability` throws on non-ok responses (rather than returning a defaults object like `getGeoSecuritySettings` does) — a failed fleet load should surface as a visible error to the admin, not silently render an empty fleet.
- Kept the component free of any offline/version-drift computation per the plan's prohibition — it renders `offline_agents`/`version_drift` arrays and counts exactly as returned by the endpoint.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. `npx tsc --noEmit` was clean for all project files (the only reported errors are in vendored `servers/` and `github-mcp-server/` submodules — pre-existing, unrelated to this plan's files, confirmed via `git status --short` showing those as pre-existing submodule diffs, not touched by this plan). `npm run build` succeeded, emitting a separate `FleetObservabilityDashboard-*.js` chunk confirming the lazy-import code-splitting works.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- FOBS-03 UI is complete: the Fleet Observability nav page is registered, gated by `manage:agents`, and renders the 48-03 aggregate endpoint.
- Manual UAT (end-of-phase, per plan's own verification note) still needed: confirm the sidebar entry appears/opens correctly for a `manage:agents` holder and is hidden/unreachable for a user without it, against a running backend with real offline/drifted agents.
- This closes out FOBS-03 and, combined with 48-01/48-02 (uptime) and 48-04 (metrics charts), completes the Phase 48 Fleet Observability & Uptime Rollups milestone scope.

---
*Phase: 48-fleet-observability-uptime-rollups*
*Completed: 2026-07-29*

## Self-Check: PASSED

All created/modified files confirmed present on disk; both commit hashes (0f2a23b, 726fa39) confirmed present in `git log --all`.
