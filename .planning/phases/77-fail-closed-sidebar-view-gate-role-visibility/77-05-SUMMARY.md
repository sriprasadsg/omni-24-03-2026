---
phase: 77-fail-closed-sidebar-view-gate-role-visibility
plan: 05
subsystem: ui
tags: [rbac, permission-refresh, zero-access, logout-timeout, fail-closed]
requires:
  - phase: 77-02
    provides: evaluateViewAccess, landingView, hasAnyScreen, permissionsKnown, NoAccessPanel/ViewGate
provides:
  - utils/permissionRefresh.ts (403 signal, leading-plus-trailing debounce, samePermissionSet, lostAccess, RefreshResult)
  - tri-state shared-in-flight refreshPermissions in App.tsx with 403 and window-focus triggers
  - components/ZeroAccessScreen.tsx (D-07 full-page screen with Retry and Sign out)
  - logoutSession 5 s abort (LOGOUT_TIMEOUT_MS)
affects: [77-08, 77-09, 77-11, 77-12, 77-13, sidebar]
status: complete
commits: 2
plan_head_before: c44bb5f6e5f9e8d859bbbcebaf18e38a023da916
plan_head_after: f28cf7a8ff1d5ee0bfe7517f93bf59b023c280a1
actuals:
  tokens: 7443
  tasks: 2
  commits: 2
tech-stack:
  added: []
  patterns:
    - "leading-plus-trailing debounce window for a noisy signal (at most two refreshes per 15 s)"
    - "refresh never widens access: error keeps the last set, an unknown list becomes empty"
key-files:
  created:
    - utils/permissionRefresh.ts
    - components/ZeroAccessScreen.tsx
    - src/__tests__/permissionRefresh.test.ts
  modified:
    - App.tsx
    - services/apiService.ts
    - src/__tests__/NoAccessScreens.test.tsx
key-decisions:
  - "Reused the existing currentUserRef/currentViewRef in App.tsx instead of adding second refs, so refreshPermissions reads the latest user and view without re-registering listeners"
  - "The landing effect re-arms (landedFor cleared) while the zero-access screen shows, and records landedFor only when it chose a view, so a Retry that makes a screen available lands on D-06/D-12 with no toast"
  - "Sign out is never gated by Retry; logoutSession aborts its request after 5 s and clears local tokens regardless"
requirements-completed: []
---

# Phase 77 Plan 05: Permission refresh on 403/focus and zero-access screen Summary

A plain 403 or a window focus now re-reads the signed-in user's permissions (a role edit reaches an open session without re-login), the open screen swaps to the access-changed panel when access is removed, and a user whose role allows no screen gets a full-page zero-access screen with a working Retry and a Sign out that cannot hang.

## Accomplishments

- **Task 1 (tracer), commit 6db1c9a3f:** `utils/permissionRefresh.ts` with `shouldSignalPermissionDenied` (403, no `X-MFA-Required`, URL not under `/api/auth/`), `notifyPermissionDenied` (leading plus trailing debounce, 15 s window), `samePermissionSet`, `lostAccess`, `RefreshResult`. `authFetch` calls `notifyPermissionDenied()` after the MFA 403 block and returns the response unchanged (silent, no toast). `refreshPermissions` in App.tsx returns `'changed' | 'same' | 'error'`, shares one in-flight promise, keeps the last list on error, reloads app data when the list changed, and sets `accessChanged` only when `lostAccess` for the open view. One effect listens for `omni:permission-denied` and window `focus` (independent of `isBackendConnected`). `handleSetCurrentView` clears `accessChanged`; `ViewGate` receives it.
- **Task 2, commit f28cf7a8f:** `ZeroAccessScreen` (brand tile, h1 focused on mount, identity dl with titled truncated values, Retry tri-state with `aria-label="Retry permission check"`, Sign out never disabled, action row stacks under 400px). App.tsx returns it before the shell when `permissionsKnown && !hasAnyScreen`, so ChatFab, CharacterTourBot, InteractiveVoiceBot and CallOverlay never mount. Pitfall 13: a user with a non-list `permissions` triggers one refresh and falls to `[]` on error. `logoutSession` aborts after `LOGOUT_TIMEOUT_MS = 5000`.
- Tracer gate (interactive, end-of-phase, automated-only verify): the verify command was re-run after Task 1 (44 tests, build exit 0) before Task 2 began.

## Refresh triggers

| Trigger | Condition | Notes |
|---------|-----------|-------|
| 403 | `omni:permission-denied` from authFetch | leading edge at once; further 403s inside 15 s produce exactly one trailing refresh when the window ends |
| Window focus | `focus` event | always |
| 30 s timer, tab visibility | existing effect | still gated by `isBackendConnected` |
| Retry (zero-access) | button | shares the in-flight request |
| Unknown list | `permissionsKnown` false for a signed-in user | once per user, then fail closed to `[]` |

Debounce window: 15000 ms (`PERMISSION_DENIED_WINDOW_MS`).

## Verification

- `npx vitest run src/__tests__`: 321 passed (306 after 77-02, +15 new), 37 files.
- `npm run build`: exit 0 (dist-new/ is a build folder only; not published).
- Acceptance greps: `notifyPermissionDenied(` in apiService 1; `PERMISSION_DENIED_EVENT` in App.tsx 3; `addEventListener('focus'` 1; `accessChanged` 3; `<ZeroAccessScreen` 1; `LOGOUT_TIMEOUT_MS` 3; `Retry permission check` 1.
- Backend untouched, so the backend suite was not run.
- Human check (user-owned, after UI deploy): sign in as a user whose custom role has no permissions; the full-page screen shows email, role and tenant; Retry reports "Still no screens"; an admin grants `view:dashboard`; Retry lands on Overview; Sign out works with the backend stopped. At 320px, light and dark, no horizontal scroll (C15, backstop).

## Deviations from Plan

None - plan executed as written. Two judgement calls: (1) the plan said "add" refs for the latest user and view; App.tsx already had `currentUserRef` and `currentViewRef`, so they are reused (the first build failed on the duplicate declaration and was fixed before commit). (2) RED for Task 1 and Task 2 was the missing module / missing export; the plan is `type: execute` (not `type: tdd`), so the plan-level RED/GREEN commit-split and the red-evidence classifier do not apply, and each task is one commit as the plan and the orchestrator require.

## Requirements

ACC-06 and ACC-08 not marked complete: `requirements.ready-ids` returned 0/2 ready because other Phase 77 plans still declare them. The orchestrator marks them when the last declaring plan completes.

## Known Stubs

None.

## Threat Flags

None. T-77-15/16/17 mitigated (focus and 403 refresh; at most two refreshes per window with a shared in-flight request and `/api/auth/` excluded; 5 s logout abort). PROH-77-05 holds in code: `'error'` keeps the last delivered set and an unknown list becomes empty, never all. The backend guard stays the enforcement point.

## Self-Check: PASSED

- Files exist: utils/permissionRefresh.ts, components/ZeroAccessScreen.tsx, src/__tests__/permissionRefresh.test.ts.
- Commits 6db1c9a3f and f28cf7a8f are ancestors of HEAD.
- Pre-existing unrelated working-tree changes were not staged; App.tsx and services/apiService.ts carried no prior edits.
