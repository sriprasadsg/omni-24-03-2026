---
phase: 77-fail-closed-sidebar-view-gate-role-visibility
verified: 2026-10-19T17:10:00Z
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
  - utils/permissionRefresh.ts
  - utils/viewAccess.ts
covered_digest: "v3:sha256:c064a7416f18a8fc656f72cee6f02cf7323309329356682165c4314731c97035"
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "Deploy (backend restart + UI publish), then in two browser sessions: sign in as a user holding a custom role, have an admin add a catalogue permission (e.g. a view:X) to that role, then focus the first window (or trigger a 403)."
    expected: "The new catalogue appears in the first user's sidebar without logging out. Note the newly unlocked screen's list data may stay empty until the next 30 s tick (WR-01) until that warning is fixed."
    why_human: "Needs the live deployed backend and UI bundle and two sessions; unit tests cover the refresh helper and gate but not the end-to-end flow."
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
**Re-verification:** No, initial verification

## Goal Achievement

### Observable Truths (ROADMAP success criteria, the contract)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A catalogue the user lacks permission for is absent from the sidebar, and reaching it by URL hash, deep link, or any in-app navigation shows a no-access state; no fail-open fallback | VERIFIED | `utils/viewAccess.ts` `evaluateViewAccess` denies unmapped views for everyone (including Super Admin), denies on a missing permission or a `screen-off:` marker. `components/Sidebar.tsx:246` filters every item through `evaluateViewAccess` and renders nothing until `permissionsKnown` (skeleton rows at 308-325). `App.tsx:1953` wraps `renderView` in `ViewGate`; `handleSetCurrentView` (1213) only moves the view and the hash handler (437) goes through it, so every path reaches the gate. `ViewGate` returns `SkeletonDashboard` while permissions are unknown and `NoAccessPanel` when denied; nothing of the denied screen mounts. Pitfall 13: a non-list permissions field gets one refresh and then becomes `[]` (App.tsx 1068-1077). 6 targeted vitest files (114 tests) pass. |
| 2 | A user with no permitted catalogue sees a clear no-access state with a guaranteed landing view and working Sign out; an `itam_viewer` without `view:dashboard` still lands somewhere valid | VERIFIED | `landingView` (viewAccess.ts) prefers dashboard then itam, then the first allowed manifest item; `viewAccess.test.ts:86` asserts `itam_viewer` lands on `itam`. `App.tsx:1634-1648` replaces the whole shell with `ZeroAccessScreen` (Retry via `refreshPermissions`, Sign out via `handleLogout`) when permissions are known but `hasAnyScreen` is false, so no empty sidebar and no floating widgets. Plan 77-05 makes sign-out abort after 5 s and clear the local session. |
| 3 | An admin opens a "what can this role see" view and sees, per role, which catalogues it can access, matching what the backend enforces | VERIFIED | `backend/role_visibility.py` computes visibility with `rbac_service`-equivalent pipeline (effective perms, `deliverable_closure`, `tenant_features.apply_tenant`), not a second rule set. Served by `GET /api/roles/{id}/visibility` (`role_endpoints.py:291`, inherits the role-management guard). UI: `services/roleApi.ts` `fetchRoleVisibility` -> `components/RoleVisibilityPanel.tsx`, mounted in `components/SettingsRolesTab.tsx:155`; the panel renders the server payload (PROH-77-07). 137 backend tests across `test_role_visibility`, `test_role_tenant_isolation`, `test_closure_delivery`, `test_role_routes_real_app` pass. |
| 4 | After an admin edits a role's permissions, the affected user's sidebar updates on next window focus or 403, without re-login | VERIFIED (with warning WR-01) | `services/apiService.ts:327` calls `notifyPermissionDenied()` on a plain 403 (leading plus trailing 15 s debounce in `utils/permissionRefresh.ts`); `App.tsx:833-840` listens for that event and `window` `focus` and runs `refreshPermissions`, which fetches `/me` permissions, keeps the last set on error, and calls `setCurrentUser(next)`. Sidebar, `ViewGate` and `ZeroAccessScreen` are all derived from `currentUser`, so they re-render from the new list. Backend side: the next `/auth/me` returns the edited role contents (test_role_write_api, per plan 77-03). WR-01 (below) is a real defect in the data reload that follows, but it does not stop the sidebar or gate from updating, so the criterion as written holds. |
| 5 | Regression tests prove visibility and route guards hold per role and per tenant, including super-admin and `platform-admin`, and one tenant's role edit never changes another tenant's users | VERIFIED | `test_role_tenant_isolation.py::test_tenant_a_edit_never_changes_tenant_b`, cross-tenant 404, foreign `tenantId` refused, sentinel tenants (`platform-admin`, `all`, `platform`) refused; `test_role_visibility.py` covers every super-admin spelling and platform roles never narrowed; `src/__tests__/viewAccess.test.ts:25` covers the five super-admin spellings. Orchestrator regression: vitest 413 passed, backend 4043 passed, route parity 50 passed. I re-ran the 4 backend files above (137 passed) and 6 frontend files (114 passed). |

**Score:** 5/5 truths verified (0 present, behavior-unverified). Live-system behaviour is routed to human verification below.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `utils/viewAccess.ts` | Single access decision, landing, hash resolution | VERIFIED | 98 lines, substantive, imported by App, Sidebar, NoAccessPanel, permissionRefresh |
| `components/NoAccessPanel.tsx` | In-place panel and `ViewGate` | VERIFIED | Wired at App.tsx:1953 |
| `components/ZeroAccessScreen.tsx` | Full-page zero-access screen | VERIFIED | Wired at App.tsx:1637 with Retry and Sign out |
| `utils/permissionRefresh.ts` | 403 debounce, focus refresh helpers | VERIFIED | Wired in apiService and App |
| `components/Sidebar.tsx` | Fail-closed menu on `evaluateViewAccess` | VERIFIED | Lines 246, 308, 325 |
| `backend/role_visibility.py` | Delivery-pipeline visibility | VERIFIED | Used by `role_endpoints.py` |
| `backend/role_endpoints.py` | Custom-role CRUD, catalogue, visibility | VERIFIED | Routes at 105-291, parity test green |
| `backend/rbac_defaults.py` | One closure (manage:X implies view/request) | VERIFIED | Covered by test_closure_delivery (32 tests) |
| `components/RoleVisibilityPanel.tsx` + `SettingsRolesTab.tsx` | Admin "what it can see" UI | VERIFIED | Mounted at SettingsRolesTab:155 |

### Key Link Verification

| From | To | Via | Status |
|------|----|-----|--------|
| `apiService.authFetch` | `App.refreshPermissions` | `omni:permission-denied` window event | WIRED |
| `window focus` | `App.refreshPermissions` | listener at App.tsx:835 | WIRED |
| `App.renderView` | `evaluateViewAccess` | `ViewGate` | WIRED |
| `Sidebar` | `evaluateViewAccess` | filter at Sidebar.tsx:246 | WIRED |
| `SettingsRolesTab` | `GET /api/roles/{id}/visibility` | `roleApi.fetchRoleVisibility` -> `RoleVisibilityPanel` | WIRED |
| `refreshPermissions` | `loadAllData` | `loadAllData()` after `setCurrentUser` | WIRED but reads stale `currentUserRef` (WR-01) |

### Data-Flow Trace (Level 4)

| Artifact | Data | Source | Real data | Status |
|----------|------|--------|-----------|--------|
| Sidebar / ViewGate | `currentUser.permissions` | `/login`, `/me` via `api.fetchCurrentPermissions` | Yes, server-delivered list | FLOWING |
| RoleVisibilityPanel | visibility payload | `GET /roles/{id}/visibility` -> `build_visibility` | Yes | FLOWING |
| Catalogue datasets after refresh | `loadAllData` fetch gating (`ifOn`) | `currentUserRef.current` | Stale list immediately after a refresh | HOLLOW for up to 30 s (WR-01) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Gate, sidebar, refresh, visibility panel, manifest | `npx vitest run` on viewAccess, SidebarFailClosed, NoAccessScreens, permissionRefresh, RoleVisibilityPanel, catalogueAccess | 6 files, 114 passed | PASS |
| Visibility, tenant isolation, closure, real-app routes | `backend/venv/bin/python -m pytest` on 4 files | 137 passed | PASS |

### Probe Execution

Step 7c: SKIPPED (no probes declared by this phase's plans).

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|--------------|-------------|--------|----------|
| ACC-06 | 77-01, 77-02, 77-05, 77-08, 77-13 | Fail-closed sidebar, render-time gate, no-access / zero-access state | SATISFIED | Truths 1 and 2 |
| ACC-07 | 77-07, 77-09 | Admin "what can this role see" view | SATISFIED | Truth 3 |
| ACC-08 | 77-03, 77-05, 77-11, 77-12 | Refresh permissions on 403 and window focus | SATISFIED (WR-01 warning) | Truth 4 |
| ACC-09 | 77-01, 77-03, 77-04, 77-06, 77-07, 77-10, 77-12 | Regression tests per role, tenant, super-admin / platform-admin | SATISFIED | Truth 5 |

All four IDs in the phase declaration appear in PLAN frontmatter and in REQUIREMENTS.md (lines 16-19, traceability 66-69); no orphaned requirements for Phase 77.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `App.tsx` | 821-822 | WR-01: `setCurrentUser(next); loadAllData();` without first setting `currentUserRef.current = next`; every sign-in path (612, 658, 751) sets the ref first, and `loadAllData` reads the ref at line 488 | Warning | After a refresh that grants access, the newly unlocked catalogue's fetches are skipped by `ifOn`/`canReadView` against the old list, so its data stays empty until the next 30 s tick or visibility change. After a refresh that removes access, the reload fires requests that now 403 and re-open a refresh window. The sidebar, gate and zero-access screen still update correctly because they derive from state. |
| `utils/viewAccess.ts` | resolveHashView | WR-06: `HASH_ALIASES[wanted]` returns inherited `Object.prototype` members for `#constructor` / `#__proto__` | Warning | Fails closed: the non-view value is unmapped and gets the no-access panel, so no access leak. |
| `backend/authentication_service.py` | 104-136 | WR-02 / WR-03: sync `mfa_required_for` fails closed for non-admin custom roles on a cold cache (WebSocket refusal); MFA role cache is not invalidated on role edit (60 s per-worker window) | Warning | Not part of the 5 criteria; reliability and a bounded enforcement lag for admin-tier permission additions. |
| `backend/role_endpoints.py` etc. | n/a | WR-04, WR-05, WR-07, IN-01..06 | Warning / Info | Open items in `77-REVIEW-DISPOSITION.md`; none breaks a roadmap criterion. WR-05 (role_usage scan capped at 5000) weakens delete-refusal for very large tenants. |

No unreferenced TBD/FIXME/XXX markers in the phase's primary files. `git status` shows mode-only changes (zero content diff) on `backend/role_assignment.py`, `utils/catalogueAccess.ts`, `utils/permissions.ts`.

### Judgment on WR-01 (requested by orchestrator)

Confirmed against source: `refreshPermissions` (App.tsx 812-823) never assigns `currentUserRef.current` before calling `loadAllData`, while `loadAllData` reads the ref synchronously at line 488 and the ref is only reassigned during render (line 280). It does not undermine ACC-08 as the roadmap states it: SC4 says the user's sidebar updates on focus or 403, and the sidebar, `ViewGate` and `ZeroAccessScreen` all derive from `currentUser` state, which is set correctly. The defect degrades the "takes effect" experience for granted catalogues (empty data for up to 30 s) and causes a redundant 403 round after a removal. It is a genuine one-line fix (`currentUserRef.current = next;` before `setCurrentUser(next)`, same as the sign-in paths) and should be applied before the UI is published, but it is a warning, not a blocker. It is not recorded under `gaps:` because the stated truth is met; if the maintainer prefers to treat the plan truth "reloads app data when the list changed" as unmet, re-run `/gsd-plan-phase 77 --gaps` for that single fix.

### Human Verification Required

1. **Two-session role edit refresh** — Test: deploy, edit a role in one session, focus the other. Expected: sidebar updates without re-login. Why human: needs the live deployed system.
2. **Restricted roles on the live system** — Test: itam_viewer and a zero-screen custom role walk the sidebar, hashes and chat navigation. Expected: forbidden items absent, in-place panel on deep links, zero-access screen with Retry and Sign out, no raw 403 toasts. Why human: real-role browser behaviour.
3. **Layout at 320/375/768 px, light and dark** — Expected: no horizontal scroll, action row stacks under 400 px. Why human: visual.
4. **Super Admin visibility panel vs. actual sidebar** — Expected: per-role lists match what holders see. Why human: live data comparison.

### Gaps Summary

No roadmap success criterion failed. All five are verified in code and by passing targeted tests (and the orchestrator's full-suite regression). Status is `human_needed` because four checks need the deployed system or visual inspection (the backend has not been restarted and the UI bundle is not published). Recommended before deploy: fix WR-01 (one line in `App.tsx`), and consider WR-02 and WR-03 (MFA cache) since they affect WebSocket reliability and the edit-to-enforcement window for admin-tier permissions.

---

_Verified: 2026-10-19_
_Verifier: Claude (gsd-verifier)_
