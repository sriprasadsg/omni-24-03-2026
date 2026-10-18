---
phase: 77-fail-closed-sidebar-view-gate-role-visibility
plan: 02
subsystem: ui
tags: [rbac, view-gate, no-access-panel, landing-view, fail-closed]
requires:
  - phase: 76
    provides: catalogue-access manifest (catalogueFor, NAV_GROUPS, viewForHash)
  - phase: 77-01
    provides: server-delivered D-11 closure and screen-off markers
provides:
  - utils/viewAccess.ts (evaluateViewAccess, landingView, hasAnyScreen, permissionsKnown, resolveHashView, LANDING_PREFERENCE)
  - components/NoAccessPanel.tsx (NoAccessPanel, ViewGate)
  - render-time fail-closed gate around renderView in App.tsx
affects: [77-05, 77-13, sidebar, permission refresh]
status: complete
plan_head_before: a05d4b03905d55c9af7fb1a76cf9ccb100ce49cc
plan_head_after: d3f648776fd684168ab42c9c528e12c5a36c9a55
actuals:
  tokens: 14000
  tasks: 2
  commits: 2
tech-stack:
  added: []
  patterns:
    - "one pure access function (evaluateViewAccess) applied at render time by ViewGate; navigation never decides access"
    - "panel is derived state: re-evaluates on every permission change, no fetch of its own"
key-files:
  created:
    - utils/viewAccess.ts
    - components/NoAccessPanel.tsx
    - src/__tests__/viewAccess.test.ts
    - src/__tests__/NoAccessScreens.test.tsx
  modified:
    - App.tsx
    - src/__tests__/catalogueAccess.test.ts
key-decisions:
  - "Platform roles skip the screen-off marker for the reason decision as well (a missing permission is always 'role' for them)"
  - "Landing effect computes landingView directly from the user it is landing, so it does not re-run on landing-memo changes"
requirements-completed: []
---

# Phase 77 Plan 02: Render-time view gate and landing rule Summary

Every screen the signed-in role cannot see is now replaced inside `<main>` by the D-05 no-access panel, decided by one pure function (`evaluateViewAccess`); sidebar and header stay and nothing of the denied screen mounts.

## Accomplishments

- **Task 1 (tracer), commit fb907052d:** `utils/viewAccess.ts` (unmapped denied for everyone including Super Admin, role / switched_off reasons, all five super-admin spellings and a delivered `*` allowed, platform roles skip screen switches), `components/NoAccessPanel.tsx` (three reason variants, access-changed notice, heading focused on mount, one "Go to {landing label}" button, skeleton while permissions unknown), `<ViewGate>` wrapped around `renderView` in App.tsx, `currentScreenOff` and its redirect effect deleted, the `renderView` default branch now returns the unmapped panel instead of the Dashboard.
- **Task 2, commit d3f648776:** `resolveHashView` (friendly-URL map moved out of App.tsx), then the navigation paths below.
- Tracer gate (interactive, end-of-phase, automated-only verify): the verify command was re-run end to end after Task 1 (59 tests, build 0), then Task 2 proceeded.

## Navigation paths changed in App.tsx

| Path | Before | After |
|------|--------|-------|
| URL hash / deep link | local alias map plus viewForHash, gated in handleSetCurrentView | `resolveHashView`; a denied hash shows the panel |
| `handleSetCurrentView` | permission branch plus silent console.warn | closes mobile sidebar and always sets the view; no access decision, no warning |
| ChatAssistant `onNavigate` | raw `setCurrentView` | `handleSetCurrentView(view as AppView)` |
| Socket compliance alert | unconditional `setCurrentView('compliance')` | navigates only when `evaluateViewAccess('compliance', ...)` is allowed |
| `handleLogin`, `registerTenant` | forced `'dashboard'` | no forced view; the landing effect picks it |
| Post-login / session restore / signup | stayed on initial `'dashboard'` | one-time landing per `email|tenantId`: hash view if the hash names one, else `landingView`; `<main>` shows `SkeletonDashboard` until landed |
| Switched-off current screen | redirect effect to first allowed item | `switched_off` panel from the gate |
| `renderView` default branch | rendered Dashboard | unmapped no-access panel |
| "Go to {landing}" button | n/a | `goToLanding`: `history.replaceState` to `#landing` then `handleSetCurrentView` (Back does not loop) |

## Landing result per role (D-06/D-12)

Covered by named vitest cases and the plan's measured table: itam_admin, itam_user, itam_viewer -> `itam` (even though assetManagement precedes itam in the menu); platform_billing -> `auditLog`; roles holding view:dashboard -> `dashboard`; a role with an empty list -> `null` (full-page zero-access screen is plan 77-05).

## Verification

- `npx vitest run src/__tests__`: 306 passed (baseline 266, +40 new tests), 36 files.
- `npm run build`: exit 0 (dist-new/ is a build folder only; not published).
- Acceptance greps: `<ViewGate` 1, `reason="unmapped"` in App.tsx 1, `export function evaluateViewAccess` 1, `export function resolveHashView` 1, `resolveHashView(` in App.tsx 2, `landingView(` in App.tsx 2, `onNavigate={(view) => handleSetCurrentView` 1.
- Human check (user-owned, after UI deploy): sign in as itam_viewer, confirm landing on IT Asset Management; open `#compliance`, expect "You don't have access to Compliance" with "Go to IT Asset Management"; press it and confirm Back does not return to the panel.

## Deviations from Plan

None - plan executed as written. One judgement call: the landing effect calls `landingView(currentUser, derivePermissionState(currentUser).hasPermission)` itself rather than reading the memoised `landing`, which keeps the effect from re-running when the memo changes and satisfies the acceptance grep (`landingView(` at least 2).

## Requirements

ACC-06 not marked complete: `requirements.ready-ids` returned 0/1 ready because other Phase 77 plans (the fail-closed sidebar, 77-13) still declare it. The orchestrator marks it when the last declaring plan completes.

## Known Stubs

None.

## Threat Flags

None. No new endpoints or auth paths; T-77-03 mitigated (render-time gate, unmapped default panel, chat and socket paths routed, source guards in catalogueAccess.test.ts). The backend guard stays the enforcement point.

## Self-Check: PASSED

- Files exist: utils/viewAccess.ts, components/NoAccessPanel.tsx, both new test files.
- Commits fb907052d and d3f648776 are ancestors of HEAD.
