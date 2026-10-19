---
phase: 77-fail-closed-sidebar-view-gate-role-visibility
verified: 2026-10-19T17:30:00Z
status: human_needed
score: 5/5 must-haves verified
covered_files:
  - .planning/phases/77-fail-closed-sidebar-view-gate-role-visibility/77-01-PLAN.md
  - .planning/phases/77-fail-closed-sidebar-view-gate-role-visibility/77-01-SUMMARY.md
  - .planning/phases/77-fail-closed-sidebar-view-gate-role-visibility/77-02-PLAN.md
  - .planning/phases/77-fail-closed-sidebar-view-gate-role-visibility/77-02-SUMMARY.md
  - .planning/phases/77-fail-closed-sidebar-view-gate-role-visibility/77-03-PLAN.md
  - .planning/phases/77-fail-closed-sidebar-view-gate-role-visibility/77-03-SUMMARY.md
  - .planning/phases/77-fail-closed-sidebar-view-gate-role-visibility/77-04-PLAN.md
  - .planning/phases/77-fail-closed-sidebar-view-gate-role-visibility/77-04-SUMMARY.md
  - .planning/phases/77-fail-closed-sidebar-view-gate-role-visibility/77-05-PLAN.md
  - .planning/phases/77-fail-closed-sidebar-view-gate-role-visibility/77-05-SUMMARY.md
  - .planning/phases/77-fail-closed-sidebar-view-gate-role-visibility/77-06-PLAN.md
  - .planning/phases/77-fail-closed-sidebar-view-gate-role-visibility/77-06-SUMMARY.md
  - .planning/phases/77-fail-closed-sidebar-view-gate-role-visibility/77-07-PLAN.md
  - .planning/phases/77-fail-closed-sidebar-view-gate-role-visibility/77-07-SUMMARY.md
  - .planning/phases/77-fail-closed-sidebar-view-gate-role-visibility/77-08-PLAN.md
  - .planning/phases/77-fail-closed-sidebar-view-gate-role-visibility/77-08-SUMMARY.md
  - .planning/phases/77-fail-closed-sidebar-view-gate-role-visibility/77-09-PLAN.md
  - .planning/phases/77-fail-closed-sidebar-view-gate-role-visibility/77-09-SUMMARY.md
  - .planning/phases/77-fail-closed-sidebar-view-gate-role-visibility/77-10-PLAN.md
  - .planning/phases/77-fail-closed-sidebar-view-gate-role-visibility/77-10-SUMMARY.md
  - .planning/phases/77-fail-closed-sidebar-view-gate-role-visibility/77-11-PLAN.md
  - .planning/phases/77-fail-closed-sidebar-view-gate-role-visibility/77-11-SUMMARY.md
  - .planning/phases/77-fail-closed-sidebar-view-gate-role-visibility/77-12-PLAN.md
  - .planning/phases/77-fail-closed-sidebar-view-gate-role-visibility/77-12-SUMMARY.md
  - .planning/phases/77-fail-closed-sidebar-view-gate-role-visibility/77-13-PLAN.md
  - .planning/phases/77-fail-closed-sidebar-view-gate-role-visibility/77-13-SUMMARY.md
  - App.tsx
  - backend/rbac_defaults.py
  - backend/role_endpoints.py
  - backend/role_visibility.py
  - components/NoAccessPanel.tsx
  - components/RoleVisibilityPanel.tsx
  - components/Sidebar.tsx
  - components/ZeroAccessScreen.tsx
  - services/apiService.ts
  - src/__tests__/catalogueAccess.test.ts
  - src/__tests__/permissionRefresh.test.ts
  - utils/permissionRefresh.ts
  - utils/viewAccess.ts
covered_digest: "v3:sha256:c36eab38ab92f91ff990cceb56ad60fe626140c33ece95915e10dba8aa941b7e"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: 5/5
  previous_verified: 2026-10-19T17:10:00Z
  gaps_closed:
    - "WR-01: refreshPermissions reloaded app data with the pre-refresh permission list (fixed a1f4488d1)"
    - "WR-08: the 30 s tick and visibilitychange started a stale-list load beside the refresh (fixed b76b8af8d)"
    - "WR-09: the periodic load waited on an /auth/me with no timeout or rejection handling (fixed 41fb29db5)"
    - "WR-10: aborting a slow /auth/me after a 401 retry would end a valid session (fixed 3bb575186)"
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "Deploy (backend restart + UI publish), then in two browser sessions: sign in as a user holding a custom role, have an admin add a catalogue permission (e.g. a view:X) to that role, then focus the first window (or trigger a 403)."
    expected: "The new catalogue appears in the first user's sidebar without logging out, and its list data loads straight away (the refresh now reloads with the refreshed list, WR-01 fixed). Repeat with a removal: the open screen swaps to the in-place no-access panel with the 'access changed' note."
    why_human: "Needs the live deployed backend and UI bundle and two sessions. The App-level wiring (focus/403 event to refreshPermissions to setCurrentUser to loadAllData) is guarded by a source-order test and traced by reading, not by a mounted-App test."
  - test: "Sign in as a restricted role (for example itam_viewer, and a custom role with no screens) on the deployed system and walk the sidebar, URL hashes (#users, #settings), and chat/socket-driven navigation."
    expected: "Forbidden catalogues are absent from the sidebar, hash and deep links show the in-place no-access panel, a role with zero screens gets the full-page zero-access screen with working Retry and Sign out, and no raw 403 toasts or offline banners appear."
    why_human: "Real-role browser behaviour against live permissions; requires visual and interactive inspection."
  - test: "Open the no-access panel, zero-access screen, and Settings > Roles 'What it can see' panel at 320, 375 and 768 px, light and dark."
    expected: "No horizontal scroll; action row stacks under 400 px; truncation and wrapping per UI-SPEC C11-C16."
    why_human: "Visual layout cannot be asserted by grep or jsdom."
  - test: "As Super Admin, open Settings > Roles, pick a tenant, and open 'What it can see' for built-in and custom roles; compare against what a user of that role actually sees."
    expected: "Per-role lists match the sidebar the role's holders see (the endpoint reuses the delivery pipeline, so they should be identical)."
    why_human: "Live-data comparison on the deployed system."
---

# Phase 77: Fail-Closed Sidebar, View Gate & Role Visibility Verification Report

**Phase Goal:** A user sees, can reach, and is told about exactly the catalogues their role allows, and a role-permission edit takes effect without a full re-login.
**Verified:** 2026-10-19
**Status:** human_needed
**Re-verification:** Yes. The prior report (human_needed, 5/5, 324b957c9) went stale when WR-01, WR-08, WR-09 and WR-10 fixes landed in `App.tsx`, `utils/permissionRefresh.ts` and `services/apiService.ts`. Truth 4 (ACC-08) was re-checked in full against the current code; the other four truths got a regression check (no source change since the prior report in their files; targeted tests re-run).

## Goal Achievement

### Observable Truths (ROADMAP success criteria, the contract)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A catalogue the user lacks permission for is absent from the sidebar, and reaching it by URL hash, deep link, or any in-app navigation shows a no-access state; no fail-open fallback | VERIFIED | Unchanged since the prior report: `utils/viewAccess.ts` `evaluateViewAccess` denies unmapped views and missing permissions; `components/Sidebar.tsx` filters through it; `App.tsx` wraps `renderView` in `ViewGate`; `loadAllData`'s `ifOn` requests nothing without a known user. `viewAccess.test.ts`, `SidebarFailClosed.test.tsx`, `NoAccessScreens.test.tsx`, `catalogueAccess.test.ts` pass in this round. |
| 2 | A user with no permitted catalogue sees a clear no-access state with a guaranteed landing view and working Sign out; an `itam_viewer` without `view:dashboard` still lands somewhere valid | VERIFIED | Unchanged: `landingView` in `viewAccess.ts`, `ZeroAccessScreen` with Retry (`refreshPermissions`) and Sign out. Pitfall 13 (App.tsx 1066-1078) still turns a non-list permissions field into `[]` after one refresh. Tests pass. |
| 3 | An admin opens a "what can this role see" view and sees, per role, which catalogues it can access, matching what the backend enforces | VERIFIED | Backend files untouched since the prior report (`git diff 324b957c9 HEAD` shows only App.tsx, apiService.ts, permissionRefresh.ts changed). Re-ran `test_role_visibility`, `test_role_tenant_isolation`, `test_closure_delivery`, `test_role_routes_real_app`: 137 passed. `RoleVisibilityPanel.test.tsx` passes. |
| 4 | After an admin edits a role's permissions, the affected user's sidebar updates on next window focus or 403, without re-login | VERIFIED | Full chain re-read in current code (details below). Sidebar, gate and zero-access screen update from `setCurrentUser(next)`; the data reload that follows now sees the refreshed list (WR-01 fixed); the periodic path no longer races a stale-list load against the refreshed one (WR-08); a stalled or failing `/auth/me` neither blocks the periodic load nor ends the session (WR-09, WR-10). Behavioural tests cover the debounce, the 403 signal, `refreshThenLoad`, the 10 s limit and the 401-retry case; the App-level glue is guarded by a source-order test only (see Evidence Level). |
| 5 | Regression tests prove visibility and route guards hold per role and per tenant, including super-admin and `platform-admin`, and one tenant's role edit never changes another tenant's users | VERIFIED | Backend isolation/visibility suites re-run green (137 passed); `viewAccess.test.ts` covers the super-admin spellings. Orchestrator regression this round: vitest 420 passed (44 files), backend 4043 passed / 47 skipped at a commit with identical backend files, build OK. |

**Score:** 5/5 truths verified (0 present, behavior-unverified). Live-system behaviour is routed to human verification below.

### Truth 4 re-check (ACC-08), current code

Path 1, 403: `services/apiService.ts` `authFetch` calls `notifyPermissionDenied()` for a plain 403 (`shouldSignalPermissionDenied` excludes MFA-gated responses and `/api/auth/`). `utils/permissionRefresh.ts` dispatches `omni:permission-denied` immediately, then at most once more at the end of a 15 s window. `App.tsx:834-838` listens for it and calls `refreshPermissions`.

Path 2, focus: the same effect listens for `window` `focus` and calls `refreshPermissions`.

Path 3, periodic/visibility: `App.tsx:847` now calls `refreshThenLoad(refreshPermissions, loadAllData)` on the 30 s tick (visible tab only) and on `visibilitychange`.

`refreshPermissions` (App.tsx 812-831): shares one in-flight promise; reads `api.fetchCurrentPermissions()`; returns `'error'` when the read fails or no user is held (last set kept, never widened); returns `'same'` for an order-insensitive equal list; otherwise builds `next`, flags `accessChanged` if the open view was lost, sets `currentUserRef.current = next` (line 821), then `setCurrentUser(next)` and `loadAllData()`, returning `'changed'`.

- WR-01 re-evaluation: `loadAllData` (line 473, `useCallback`) has no `await` before it reads `currentUserRef.current` (line 488), so the synchronous ref assignment at 821 guarantees `ifOn`/`canReadView` use the refreshed list. The sign-in paths (612, 658, 751) use the same pattern. The key link `refreshPermissions -> loadAllData` is now WIRED with the correct list; the "HOLLOW for up to 30 s" data-flow row from the previous report is resolved to FLOWING.
- WR-08: on `'changed'` the refresh's own load is the only load; on `'same'` or `'error'` exactly one load runs. A tick that joins a focus/403 refresh in flight gets the same result, so no duplicate.
- WR-09/WR-10: `fetchCurrentPermissions` (apiService.ts 756-780) races the read against a 10 s timer (`PERMISSIONS_TIMEOUT_MS`) and resolves `null` (so `'error'`); it does not abort, so `authFetch`'s 401 retry cannot end a valid session. `refreshThenLoad` treats a rejected refresh as `'error'` and still loads.
- Residual (not a defect against the criterion): a `loadAllData` already in flight when a refresh changes the list (a previous tick's load, the reconnect load, the initial-load effect) is still unordered against the new load because `loadAllData` has no sequence token (REVIEW WR-08 resolution note, IN-08). The window is narrow and the sidebar/gate are unaffected because they derive from `currentUser`.

Evidence level: the App-level glue (event -> `refreshPermissions` -> `setCurrentUser` -> `loadAllData`) has no mounted-App test; the ordering at line 821 is guarded by `catalogueAccess.test.ts` as a source-text order check (REVIEW IN-07 notes it is brittle). Every component the glue calls (debounce, 403 signal, `refreshThenLoad`, timeout, `lostAccess`, sidebar/gate derivation from the permission list) has behavioural tests. I traced the glue by reading and checked the synchronous-read property directly, so the truth is marked VERIFIED; the end-to-end behaviour stays in human item 1.

### Deferred Items

None. Later milestone phases (78-80) cover cost work, not access.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `utils/viewAccess.ts` | Single access decision, landing, hash resolution | VERIFIED | Substantive, imported by App, Sidebar, NoAccessPanel, permissionRefresh |
| `components/NoAccessPanel.tsx` | In-place panel and `ViewGate` | VERIFIED | Wired in App.tsx `renderView` |
| `components/ZeroAccessScreen.tsx` | Full-page zero-access screen | VERIFIED | Wired with Retry (`refreshPermissions`) and Sign out |
| `utils/permissionRefresh.ts` | 403 debounce, `refreshThenLoad`, `lostAccess`, `samePermissionSet` | VERIFIED | Imported by App.tsx:243 and apiService; all exports used |
| `services/apiService.ts` `fetchCurrentPermissions` | Bounded permission read | VERIFIED | 10 s race, no abort, called from `refreshPermissions` |
| `components/Sidebar.tsx` | Fail-closed menu on `evaluateViewAccess` | VERIFIED | Filter plus skeleton until permissions known |
| `backend/role_visibility.py`, `role_endpoints.py`, `rbac_defaults.py` | Delivery-pipeline visibility, role CRUD, one closure | VERIFIED | Unchanged; 137 backend tests green |
| `components/RoleVisibilityPanel.tsx` + `SettingsRolesTab.tsx` | Admin "what it can see" UI | VERIFIED | Mounted in SettingsRolesTab; panel test passes |

### Key Link Verification

| From | To | Via | Status |
|------|----|-----|--------|
| `apiService.authFetch` | `App.refreshPermissions` | `omni:permission-denied` window event | WIRED |
| `window focus` | `App.refreshPermissions` | listener at App.tsx:835 | WIRED |
| 30 s tick / `visibilitychange` | `refreshPermissions` then `loadAllData` | `refreshThenLoad` (App.tsx:847) | WIRED |
| `refreshPermissions` | `loadAllData` | `currentUserRef.current = next` (821) before `loadAllData()` (823); `loadAllData` reads the ref at 488 with no prior await | WIRED (WR-01 resolved) |
| `refreshPermissions` | `api.fetchCurrentPermissions` | bounded 10 s read | WIRED |
| `App.renderView` | `evaluateViewAccess` | `ViewGate` | WIRED |
| `Sidebar` | `evaluateViewAccess` | filter | WIRED |
| `SettingsRolesTab` | `GET /api/roles/{id}/visibility` | `roleApi.fetchRoleVisibility` -> `RoleVisibilityPanel` | WIRED |

### Data-Flow Trace (Level 4)

| Artifact | Data | Source | Real data | Status |
|----------|------|--------|-----------|--------|
| Sidebar / ViewGate | `currentUser.permissions` | `/login`, `/auth/me` via `api.fetchCurrentPermissions` | Yes, server-delivered list; error keeps last set | FLOWING |
| RoleVisibilityPanel | visibility payload | `GET /roles/{id}/visibility` -> `build_visibility` | Yes | FLOWING |
| Catalogue datasets after a refresh | `loadAllData` `ifOn` gating | `currentUserRef.current` (set to the refreshed user before the call) | Yes, refreshed list (was HOLLOW up to 30 s before a1f4488d1) | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Gate, sidebar, refresh, visibility panel, manifest, WR-01/08/09/10 behaviours | `npx vitest run` on permissionRefresh, catalogueAccess, viewAccess, SidebarFailClosed, NoAccessScreens, RoleVisibilityPanel | 6 files, 121 passed | PASS |
| Visibility, tenant isolation, closure, real-app routes | `backend/venv/bin/python -m pytest -q` on test_role_visibility, test_role_tenant_isolation, test_closure_delivery, test_role_routes_real_app | 137 passed | PASS |

Full-suite results (vitest 420 / backend 4043 / build OK) are the orchestrator's; I did not re-run the full suites.

### Probe Execution

Step 7c: SKIPPED (no probes declared by this phase's plans).

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|--------------|-------------|--------|----------|
| ACC-06 | 77-01, 77-02, 77-05, 77-08, 77-13 | Fail-closed sidebar, render-time gate, no-access / zero-access state | SATISFIED | Truths 1 and 2 |
| ACC-07 | 77-07, 77-09 | Admin "what can this role see" view | SATISFIED | Truth 3 |
| ACC-08 | 77-03, 77-05, 77-11, 77-12 | Refresh permissions on 403 and window focus | SATISFIED | Truth 4; WR-01 resolved |
| ACC-09 | 77-01, 77-03, 77-04, 77-06, 77-07, 77-10, 77-12 | Regression tests per role, tenant, super-admin / platform-admin | SATISFIED | Truth 5 |

All four IDs appear in PLAN frontmatter and in REQUIREMENTS.md (lines 16-19, traceability 66-69); no orphaned requirements for Phase 77.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `App.tsx` | 473 (`loadAllData`) | No sequence token: a load already in flight when a refresh changes the list can finish last and overwrite the reload (residual of WR-08; IN-08) | Warning | Narrow window, only affects dataset freshness until the next tick; sidebar and gate unaffected. |
| `src/__tests__/catalogueAccess.test.ts` | 201-211 | WR-01 guard is a source-text order check (IN-07), and several gate tests rely on source matching (IN-06) | Info | Regression protection for the ordering is weak; no mounted-App test of the refresh glue. |
| `utils/viewAccess.ts` | resolveHashView | WR-06: inherited `Object.prototype` members for `#constructor` / `#__proto__` | Warning | Fails closed (no-access panel), no access leak. |
| `backend/authentication_service.py` | 104-136 | WR-02 / WR-03: sync `mfa_required_for` fails closed for non-admin custom roles on a cold cache; MFA role cache not invalidated on role edit (60 s per worker) | Warning | Outside the 5 criteria; WebSocket reliability and a bounded enforcement lag. |
| `backend/role_endpoints.py` etc. | n/a | WR-04, WR-05, WR-07, IN-01..06 | Warning / Info | Open in `77-REVIEW-DISPOSITION.md`; none breaks a roadmap criterion. |

Review state: WR-01, WR-08, WR-09, IN-09 resolved by the reviewer; WR-10 fixed in 3bb575186 after the last review pass with a reproduction test (`permissionRefresh.test.ts`, "never ends a valid session when the retried /auth/me is the slow part") but not re-reviewed. No unreferenced TBD/FIXME/XXX in `App.tsx`, `utils/permissionRefresh.ts`, `utils/viewAccess.ts`. Working tree shows no uncommitted content changes in the phase's implementation files.

### Human Verification Required

1. **Two-session role edit refresh.** Test: deploy, edit a role (add then remove a catalogue permission) in one session, focus or trigger a 403 in the other. Expected: sidebar updates without re-login, a granted catalogue's data loads immediately (WR-01 fixed), a removal swaps the open screen to the no-access panel. Why human: live deployed system, two sessions; App-level wiring not covered by a mounted test.
2. **Restricted roles on the live system.** itam_viewer and a zero-screen custom role walk the sidebar, hashes and chat navigation. Expected: forbidden items absent, in-place panel on deep links, zero-access screen with Retry and Sign out, no raw 403 toasts.
3. **Layout at 320/375/768 px, light and dark.** Expected: no horizontal scroll, action row stacks under 400 px.
4. **Super Admin visibility panel vs. actual sidebar.** Expected: per-role lists match what holders see.

All four stay: the code now makes none unnecessary (the deployed system is not restarted or published, and none of these can be asserted in jsdom). Item 1's WR-01 lag note was removed.

### Gaps Summary

No roadmap success criterion failed and no gap is open. Re-verification confirms WR-01 is fixed in the current code (ref assigned before `setCurrentUser` and `loadAllData`, `loadAllData` reads it synchronously), the periodic path orders refresh before load (WR-08), and the permission read is bounded without aborting (WR-09, WR-10). The HOLLOW data-flow row is closed. Status stays `human_needed` because four checks need the deployed system or visual inspection (backend not restarted, UI bundle not published). Remaining open review items (WR-02..07, IN-01..08) are warnings/info outside the five criteria; WR-02 and WR-03 (MFA cache) are worth scheduling before the release that enables admin-tier custom roles in production.

---

_Verified: 2026-10-19 (re-verification)_
_Verifier: Claude (gsd-verifier)_
