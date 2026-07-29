---
phase: 47-agent-scoped-geo-security-detectors
plan: 06
subsystem: ui
tags: [react, tailwind, apiService, admin-settings, geo-security]

# Dependency graph
requires:
  - phase: 47-04
    provides: "Admin-gated GET/PATCH /api/settings/geo-security endpoints (geo_security_endpoints.py) backed by geo_security_service.get_geo_security_settings"
provides:
  - "apiService getGeoSecuritySettings/setGeoSecuritySettings clients"
  - "SecuritySettingsDashboard.tsx admin panel (detector toggles + allowlist editor)"
  - "App.tsx/Sidebar.tsx navigation wiring under 'geoSecurity'"
affects: [47-VALIDATION, GAUD-audit, GSEC-manual-uat]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Cloned getAgentLocationTracking/setAgentLocationTracking apiService shape for a new admin-settings resource"
    - "Cloned PrivacyDashboard's toggle-section Tailwind layout for a distinct Security settings surface (per D-06)"

key-files:
  created:
    - components/SecuritySettingsDashboard.tsx
  modified:
    - services/apiService.ts
    - App.tsx
    - components/Sidebar.tsx
    - types.ts
    - .gitignore

key-decisions:
  - "Kept SecuritySettingsDashboard.tsx as a new, separate component rather than folding into PrivacyDashboard.tsx per D-06 (security config distinct from privacy config)"
  - "Named export (SecuritySettingsDashboard) with a .then(m => ({ default: m.X })) lazy import, matching the majority lazy-import convention in App.tsx rather than PrivacyDashboard's default-export style"
  - "geoSecurity nav item and viewPermissionMap entry both gated on 'manage:settings' (client-side gate; backend PATCH's _require_admin is the authoritative control per T-47-06-E)"

requirements-completed: [GSEC-03]

coverage:
  - id: D1
    description: "apiService exposes getGeoSecuritySettings/setGeoSecuritySettings hitting /settings/geo-security"
    requirement: "GSEC-03"
    verification:
      - kind: unit
        ref: "npx tsc --noEmit (services/apiService.ts — no errors)"
        status: pass
    human_judgment: false
  - id: D2
    description: "New admin Security settings panel with detector toggles + allowed-country-code allowlist editor, loading current settings on mount and persisting via PATCH"
    requirement: "GSEC-03"
    verification: []
    human_judgment: true
    rationale: "Visual/interactive UI behavior (toggle persistence, allowlist add/remove, tenant isolation) requires a human driving the real app per 47-VALIDATION.md's Manual-Only gate — no automated UI test harness exists for this panel."
  - id: D3
    description: "Panel reachable via Sidebar nav entry ('Geo Security', manage:settings gated) and App.tsx 'geoSecurity' view case"
    requirement: "GSEC-03"
    verification:
      - kind: unit
        ref: "grep -c geoSecurity App.tsx components/Sidebar.tsx (1 match each) + npm run build (dedicated SecuritySettingsDashboard-*.js chunk emitted)"
        status: pass
    human_judgment: false

# Metrics
duration: 12min
completed: 2026-07-29
status: complete
---

# Phase 47 Plan 06: Security Settings Panel (Geo-Security Config UI) Summary

**New admin-gated SecuritySettingsDashboard.tsx panel with impossible-travel/geo-fence toggles and a country-code allowlist editor, wired to the Plan 47-04 `/settings/geo-security` endpoints via new apiService clients.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-29T19:11:39+05:30 (Task 1 commit)
- **Completed:** 2026-07-29T19:18:15+05:30 (Task 3 commit)
- **Tasks:** 3/3 completed
- **Files modified:** 6 (1 created, 5 modified)

## Accomplishments
- `services/apiService.ts`: added `GeoSecuritySettings` interface + `getGeoSecuritySettings()`/`setGeoSecuritySettings(settings)`, cloning the existing `getAgentLocationTracking`/`setAgentLocationTracking` graceful-fallback / throw-on-error shape, targeting `/settings/geo-security`.
- `components/SecuritySettingsDashboard.tsx` (new, 196 lines): admin panel with two toggles (impossible-travel detection; geo-fence detection, explicitly labeled alert-only/no-blocking per D-04) and an allowed-country-code allowlist editor (uppercase-normalized input + removable chip list). Loads settings on mount, persists every change immediately via PATCH, and shows success/error via the existing `showToast` utility.
- `App.tsx` + `components/Sidebar.tsx`: registered the panel behind a new `geoSecurity` view — lazy import, `ErrorBoundary`-wrapped case, and a nav entry under "Management & Settings" gated by the `manage:settings` permission (matching the backend's admin-only PATCH gate).

## Task Commits

Each task was committed atomically:

1. **Task 1: Add getGeoSecuritySettings / setGeoSecuritySettings API clients** - `e1d88b7` (feat)
2. **Task 2: Build the SecuritySettingsDashboard panel** - `5273ac1` (feat)
3. **Task 3: Register the panel in App.tsx and Sidebar.tsx** - `4ffafb3` (feat)

**Plan metadata:** (this commit, following self-check)

## Files Created/Modified
- `services/apiService.ts` - `GeoSecuritySettings` interface + `getGeoSecuritySettings`/`setGeoSecuritySettings` clients targeting `/settings/geo-security`
- `components/SecuritySettingsDashboard.tsx` - new admin panel: detector toggles + allowlist editor
- `App.tsx` - lazy import, `geoSecurity` view case, `viewPermissionMap` entry
- `components/Sidebar.tsx` - `geoSecurity` nav entry under Management & Settings
- `types.ts` - added `'geoSecurity'` to the `AppView` union (Rule 3 auto-fix, see below)
- `.gitignore` - added `dist-new` (Rule 3 auto-fix, see below)

## Decisions Made
- Distinct component (not folded into `PrivacyDashboard.tsx`) per D-06 — security detector config stays separate from privacy config.
- Named-export + `.then(m => ({ default: m.X }))` lazy-import style chosen over `PrivacyDashboard`'s default-export style, since it's the dominant convention across `App.tsx`'s ~30 other lazy imports.
- Both the nav item and `viewPermissionMap` entry gate on `manage:settings` — client-side gating is defense-in-depth only; `geo_security_endpoints.py`'s `_require_admin` on the PATCH route is the authoritative control (T-47-06-E).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added `'geoSecurity'` to the `AppView` union and `viewPermissionMap` in `App.tsx`**
- **Found during:** Task 3 (registering the panel)
- **Issue:** `types.ts`'s `AppView` union and `App.tsx`'s `Record<AppView, Permission>` `viewPermissionMap` are both exhaustive — adding a new `case 'geoSecurity'` without updating them left two `tsc` errors (`Type '"geoSecurity"' is not comparable to type 'AppView'` and `Property 'geoSecurity' is missing in type ... Record<AppView, Permission>`), which `npm run build`'s esbuild pass did not catch (only visible via `npx tsc --noEmit`, exactly as the plan's `<verify>` step specifies).
- **Fix:** Added `'geoSecurity'` to the `AppView` union in `types.ts` (adjacent to `'privacy'`) and `geoSecurity: 'manage:settings'` to `App.tsx`'s `viewPermissionMap` (adjacent to `privacy: 'view:compliance'`).
- **Files modified:** types.ts, App.tsx
- **Verification:** `npx tsc --noEmit` clean for `App.tsx`/`components/Sidebar.tsx`/`types.ts`; `npm run build` succeeds with a dedicated `SecuritySettingsDashboard-*.js` chunk emitted.
- **Committed in:** 4ffafb3 (Task 3 commit)

**2. [Rule 3 - Blocking hygiene] Added `dist-new` to `.gitignore`**
- **Found during:** Task 2 (running `npm run build` per the task's `<verify>` step)
- **Issue:** `vite.config.ts` builds to `dist-new` (documented in-repo as bypassing a permission-locked `dist/`), which was untracked and would have been left as stray untracked output after every future build in this working tree.
- **Fix:** Added `dist-new` to `.gitignore` alongside the existing `dist`/`dist-ssr` entries.
- **Files modified:** .gitignore
- **Verification:** `git status --short` no longer lists `dist-new/` as untracked after a build.
- **Committed in:** 5273ac1 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 3 — blocking `tsc`/build issues, no scope creep)
**Impact on plan:** Both fixes were necessary for the plan's own `<verify>` commands (`npx tsc --noEmit && npm run build`) to pass cleanly; neither changed the plan's functional scope.

## Issues Encountered
None beyond the two auto-fixed blocking issues above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- GSEC-03's config UI half is complete: an admin can now reach `/geoSecurity` in the sidebar, toggle both detectors, and manage the allowed-country-code allowlist, all persisted through the Plan 47-04 admin-gated backend.
- Manual/UAT browser verification (toggle a detector, add/remove a country, confirm persistence and tenant isolation as an actual admin) remains outstanding per 47-VALIDATION.md's Manual-Only gate — not exercised in a live browser this session. Surfaced at `/gsd-verify-work`.
- No blockers for the rest of Phase 47 or downstream phases (48/49 read Phase 46/47 backend artifacts, not this UI).

---
*Phase: 47-agent-scoped-geo-security-detectors*
*Completed: 2026-07-29*

## Self-Check: PASSED

All created/modified files present on disk; all 3 task commits (e1d88b7, 5273ac1, 4ffafb3) confirmed in git log.
