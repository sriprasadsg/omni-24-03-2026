---
phase: 77-fail-closed-sidebar-view-gate-role-visibility
verified: 2026-10-21T13:55:00Z
status: passed
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
  - backend/authentication_endpoints.py
  - backend/authentication_service.py
  - backend/rbac_defaults.py
  - backend/role_endpoints.py
  - backend/role_visibility.py
  - backend/tests/test_custom_role_mfa.py
  - backend/tests/test_role_write_api.py
  - backend/tests/test_websocket_connect_rate_limit.py
  - backend/websocket_manager.py
  - components/NoAccessPanel.tsx
  - components/RoleVisibilityPanel.tsx
  - components/Sidebar.tsx
  - components/ZeroAccessScreen.tsx
  - hooks/useVisibleNav.ts
  - services/apiService.ts
  - shared/catalogue-access.json
  - src/__tests__/catalogueAccess.test.ts
  - src/__tests__/permissionRefresh.test.ts
  - utils/permissionRefresh.ts
  - utils/viewAccess.ts
covered_digest: "v3:sha256:8f0bd2c5e1e1c1ef78c15a8f55d034a3ae4b9a097aebc806f4579b8595beeead"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: 5/5
  previous_verified: 2026-10-19T18:05:00Z
  gaps_closed:
    - "All five human_verification items from the previous report: closed by 77-UAT.md (5/5 pass on the live system, e70c1df0b)"
  gaps_remaining: []
  regressions: []
---

# Phase 77: Fail-Closed Sidebar, View Gate & Role Visibility Verification Report

**Phase Goal:** A user sees, can reach, and is told about exactly the catalogues their role allows, and a role-permission edit takes effect without a full re-login.
**Verified:** 2026-10-21
**Status:** passed
**Re-verification:** Yes (third). The prior report (human_needed, 5/5, 2026-10-19) went stale because non-phase work on 2026-10-20/21 changed covered files. This round re-read the changed code against each roadmap criterion and re-ran the phase tests.

## What changed since the last report

`git diff 112e62692 HEAD` over the covered files shows changes in `App.tsx`, `components/Sidebar.tsx`, `services/apiService.ts`, `backend/authentication_endpoints.py`, `backend/rbac_defaults.py`, `src/__tests__/catalogueAccess.test.ts`, plus new `hooks/useVisibleNav.ts` and an added `customDashboards` entry in `shared/catalogue-access.json`. None are Phase 77 task commits. Each was read for effect on the five criteria:

- **Sidebar filter moved to `hooks/useVisibleNav.ts`.** The filter is the old Sidebar logic: returns `[]` without a `currentUser`, calls `evaluateViewAccess(item.view, currentUser, hasPermission).allowed` for every item, and bypasses only for a resolved super admin (`isSuperAdminRoleName`) after that check. It is now shared by the Sidebar and the command palette/pinned pages, so no other surface offers a page the sidebar hides. `Sidebar.tsx` consumes it (line 184) and renders the skeleton while `permissionsKnown` is false (line 243).
- **`App.tsx`.** The gate and refresh wiring is intact: `ViewGate` wraps `renderView` (line 1967); the full-page `ZeroAccessScreen` renders when `permissionsKnown && !hasAnyScreen` (1647-1657); `refreshPermissions` (821-838) is bound to `PERMISSION_DENIED_EVENT` and `focus` (843-848), also on visibility change and the 30 s poll, and keeps the last list on error; the unknown-permissions case becomes `[]` (fail closed). New `customDashboards` view has a catalogue entry (`view:dashboard`), so it is gated, not unmapped; unmapped views still fall to `NoAccessPanel reason="unmapped"` (line 1913).
- **`backend/authentication_endpoints.py`.** Approval-gated sign-up (no session from `/auth/signup`; pending users get 403 on login). Not on the access path of this phase; `/login` and `/me` still call `session_permissions` and `mfa_action_for(required=await resolve_mfa_required(...))`.
- **`backend/rbac_defaults.py`.** Adds `manage:automl/dashboards/mlops/tracing` to the tenant admin table and `manage:backups`/`view:backups` to `SUPER_ADMIN_ONLY_PERMISSIONS`. These are table additions; the golden-set and literal-guard tests still pass.
- **`backend/tests/test_websocket_connect_rate_limit.py`** (uncommitted): import split onto two lines only. **`shared/catalogue-access.json`** (uncommitted): file mode 644 to 755 only, no content change.
- No unreferenced `TBD`/`FIXME`/`XXX` in the covered implementation files.

## Goal Achievement

### Observable Truths (ROADMAP success criteria, the contract)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A catalogue the user lacks permission for is absent from the sidebar; reaching it by hash, deep link or in-app navigation shows a no-access state; no fail-open fallback | VERIFIED | `evaluateViewAccess` denies unmapped views for everyone, honours `screen-off:` markers, and allows only super admin, `*`, or the held permission. `useVisibleNav` applies it to every item and returns `[]` with no user. `ViewGate` wraps `renderView`. Tests re-run: `viewAccess`, `SidebarFailClosed`, `NoAccessScreens`, `catalogueAccess` pass. UAT 2 (live, itam_viewer and zero-screen role): pass. |
| 2 | A user with no permitted catalogue sees a clear no-access state with a guaranteed landing view and working Sign out | VERIFIED | `ZeroAccessScreen` replaces the whole shell with Retry (`refreshPermissions`) and Sign out (`handleLogout`); `landingView` prefers dashboard, itam, then first allowed item. UAT 2 and 3 (layout at 320/375/768, light and dark): pass. |
| 3 | An admin sees, per role, which catalogues it can access, matching what the backend enforces | VERIFIED | `role_visibility.py` unchanged; `RoleVisibilityPanel` reads `GET /roles/{id}/visibility`, built from the delivery pipeline. `test_role_visibility`, `test_closure_delivery`, `test_role_routes_real_app`, `RoleVisibilityPanel.test.tsx` pass. UAT 4 (panel vs actual sidebar on the live system): pass. |
| 4 | After an admin edits a role, the affected user's sidebar updates on next focus or 403, without re-login | VERIFIED | 403 event and `focus` -> `refreshPermissions` -> `setCurrentUser` -> `loadAllData`, traced in current `App.tsx`; `permissionRefresh` tests pass. Server side: `_role_write` clears the tenant's MFA cache so the edit also reaches the MFA gate at once. UAT 1 (two sessions, add and remove) and UAT 5 (role edit puts holders behind MFA at once, socket refused until MFA): pass. |
| 5 | Regression tests prove visibility and route guards hold per role and per tenant, incl. super-admin and `platform-admin`, and one tenant's role edit never changes another tenant's users | VERIFIED | `test_role_tenant_isolation`, `test_platform_roles`, `test_auth_mfa`, `test_role_literal_guard`, `viewAccess.test.ts` pass; invalidation tests assert only the named tenant is dropped. |

**Score:** 5/5 truths verified (0 behavior-unverified). Truths 4 and the MFA half of D-14 are behavior-dependent; they have both unit tests and live UAT evidence.

### D-14 permission-based MFA (77-04)

Unchanged by the interim work except that `/login` and `/me` still pass `required=await resolve_mfa_required(...)`. `rbac_defaults.requires_mfa` stays the single predicate, `resolve_mfa_required` keeps the per-tenant generation guard, `_role_write` invalidates after each role write, and `websocket_manager.connect` awaits `verify_token_async`. `test_custom_role_mfa`, `test_role_write_api` and `test_websocket_connect_rate_limit` pass. Live behavior confirmed by UAT 5.

### Deferred Items

None. Phases 78-80 cover cost work, not access.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `utils/viewAccess.ts` | `evaluateViewAccess`, `landingView`, `permissionsKnown`, `resolveHashView` | VERIFIED | Substantive, used by App, Sidebar hook, NoAccessPanel |
| `hooks/useVisibleNav.ts` | Fail-closed nav list | VERIFIED | Wired to Sidebar and shell services |
| `components/Sidebar.tsx` | Consumes the hook, skeleton when unknown | VERIFIED | Lines 184, 243, 283 |
| `components/NoAccessPanel.tsx`, `ZeroAccessScreen.tsx` | In-place and full-page states | VERIFIED | Rendered from `App.tsx` |
| `utils/permissionRefresh.ts`, `App.tsx` `refreshPermissions` | 403/focus refresh | VERIFIED | Wired, tri-state result |
| `components/RoleVisibilityPanel.tsx`, `backend/role_visibility.py` | Per-role visibility | VERIFIED | Unchanged |
| `backend/authentication_service.py`, `role_endpoints.py`, `websocket_manager.py`, `rbac_defaults.py` | Permission-based MFA, role writes | VERIFIED | Tests pass |
| `shared/catalogue-access.json` | Manifest incl. `customDashboards` | VERIFIED | New view is mapped |

### Key Link Verification

| From | To | Via | Status |
|------|----|-----|--------|
| `Sidebar` | `useVisibleNav` -> `evaluateViewAccess` | hook call, line 184 | WIRED |
| `App.tsx` `renderView` | `ViewGate` | line 1967 | WIRED |
| 403 event / `focus` / visibility / 30 s poll | `refreshPermissions` -> `loadAllData` | listeners 843-866 | WIRED |
| `permissionsKnown && !hasAnyScreen` | `ZeroAccessScreen` | lines 1647-1657 | WIRED |
| `role_endpoints` writes | `invalidate_mfa_role_cache` | `_role_write` finally | WIRED |
| `authentication_endpoints` login and /me | `resolve_mfa_required` | `required=` | WIRED |

### Data-Flow Trace (Level 4)

| Artifact | Data | Source | Real data | Status |
|----------|------|--------|-----------|--------|
| Sidebar / ViewGate | `currentUser.permissions` | `/login`, `/auth/me` via `session_permissions` | Yes | FLOWING |
| RoleVisibilityPanel | visibility payload | `GET /roles/{id}/visibility` -> `build_visibility` | Yes | FLOWING |
| MFA requirement | `required` | `effective_permissions` over tenant role docs | Yes | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| MFA matrix, role write API, socket connect, visibility, tenant isolation, closure, real-app routes, platform roles, auth MFA, literal guard | `backend/venv/bin/python -m pytest -q` on the ten phase test files | 359 passed | PASS |
| Refresh, catalogue, view access, sidebar fail-closed, no-access screens, visibility panel | `npx vitest run` on six files | 121 passed | PASS |

Orchestrator-supplied (not re-run by me): backend phase set 889 passed, vitest `src/__tests__` 513 passed, full UI suite 836 passed, `npm run build` OK.

### Probe Execution

Step 7c: SKIPPED (no probes declared by this phase's plans).

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|--------------|-------------|--------|----------|
| ACC-06 | 77-01, 77-02, 77-05, 77-08, 77-13 | Fail-closed sidebar, render-time gate, no-access / zero-access state | SATISFIED | Truths 1, 2 |
| ACC-07 | 77-07, 77-09 | Admin "what can this role see" view | SATISFIED | Truth 3 |
| ACC-08 | 77-03, 77-05, 77-11, 77-12 | Refresh on 403 and focus; edit takes effect without re-login | SATISFIED | Truth 4 |
| ACC-09 | 77-01, 77-03, 77-04, 77-06, 77-07, 77-10, 77-12 | Regression tests per role, tenant, super-admin / platform-admin | SATISFIED | Truth 5 |

All four IDs are in REQUIREMENTS.md (lines 16-19, traceability 66-69, marked Complete). No orphaned Phase 77 requirements.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `backend/role_endpoints.py`, `utils/viewAccess.ts`, `App.tsx`, `services/apiService.ts` | n/a | Open review items WR-04..07, WR-11, IN-01..08, IN-10, IN-11, IN-13 (`77-REVIEW-DISPOSITION.md`) | Warning / Info | None breaks a roadmap criterion; WR-06 fails closed |

The incremental review (`77-REVIEW.md`, f869f7b55) found no critical issues. No debt markers in covered implementation files.

### Human Verification Required

None. The five items the previous report listed are closed by `77-UAT.md` (5 passed, 0 issues, 2026-10-21).

Residual limits, unchanged and documented: another backend worker would see a role edit after its 60 s MFA TTL (deployment is single-process); an already-open socket is re-checked only on reconnect.

### Gaps Summary

No gaps. Every roadmap success criterion is satisfied in the current code, the interim UI-shell, sign-up and dashboard work preserved the fail-closed filter, the render-time gate, the zero-access screen and the refresh wiring, phase tests pass, and live UAT closed the previously human-only checks.

---

_Verified: 2026-10-21 (re-verification)_
_Verifier: Claude (gsd-verifier)_
