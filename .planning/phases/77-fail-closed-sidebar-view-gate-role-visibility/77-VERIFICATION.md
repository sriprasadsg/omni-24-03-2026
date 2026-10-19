---
phase: 77-fail-closed-sidebar-view-gate-role-visibility
verified: 2026-10-19T18:05:00Z
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
  - services/apiService.ts
  - src/__tests__/catalogueAccess.test.ts
  - src/__tests__/permissionRefresh.test.ts
  - utils/permissionRefresh.ts
  - utils/viewAccess.ts
covered_digest: "v3:sha256:4ea20f64c82c2f81a70391bf6032daeffdd1077eb498029b7eed161efd28889d"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: 5/5
  previous_verified: 2026-10-19T17:30:00Z
  gaps_closed:
    - "WR-02: WebSocket connect used the synchronous cold-cache MFA guess (fixed bee9299ce: connect awaits verify_token_async)"
    - "WR-03: a role-permission edit reached the MFA requirement only after the 60 s cache expired, and a store error could answer less strictly than the last answer (fixed bee9299ce)"
    - "IN-12: a lookup overtaken by a role write could store its pre-edit answer (fixed 2bc310005, per-tenant generation guard)"
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "Deploy (backend restart + UI publish), then in two browser sessions: sign in as a user holding a custom role, have an admin add a catalogue permission (e.g. a view:X) to that role, then focus the first window (or trigger a 403)."
    expected: "The new catalogue appears in the first user's sidebar without logging out, and its list data loads straight away. Repeat with a removal: the open screen swaps to the in-place no-access panel with the 'access changed' note."
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
  - test: "After deploy: as a tenant admin with MFA enrolled, create a custom role with no admin-tier permission and assign it to a test user with an open session (browser tab plus live socket, no MFA enrolled). Then add manage:users to that role."
    expected: "Before the edit the user works normally and the socket connects. Right after the edit (no wait for the 60 s cache) the user's next API call is refused with the MFA-required response and the app shows the MFA enroll/verify gate; a fresh socket connect (reload the tab) is refused until MFA is passed; removing the permission again lifts it. An already-open socket is not re-checked until it reconnects."
    why_human: "Needs the restarted backend (the running process still holds the old MFA code), a real socket client, and a role edit made from the UI; the unit tests cover the logic but not the deployed wiring."
---

# Phase 77: Fail-Closed Sidebar, View Gate & Role Visibility Verification Report

**Phase Goal:** A user sees, can reach, and is told about exactly the catalogues their role allows, and a role-permission edit takes effect without a full re-login.
**Verified:** 2026-10-19
**Status:** human_needed
**Re-verification:** Yes (second re-verification). The prior report (human_needed, 5/5, f3a760ceb) went stale when bee9299ce (WR-02/WR-03) and 2bc310005 (IN-12) changed `backend/authentication_service.py`, `backend/role_endpoints.py` and `backend/websocket_manager.py`. The D-14 MFA truth and the MFA half of truth 4 were re-checked in full against the current code. Truths 1, 2, 3 and 5 got a regression check: `git diff f3a760ceb HEAD` over `App.tsx`, `components/`, `utils/`, `services/` and `src/` is empty, so the front-end files behind those truths are byte-identical to the previous report.

## Goal Achievement

### Observable Truths (ROADMAP success criteria, the contract)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A catalogue the user lacks permission for is absent from the sidebar, and reaching it by hash, deep link or in-app navigation shows a no-access state; no fail-open fallback | VERIFIED | No change to `utils/viewAccess.ts`, `components/Sidebar.tsx`, `App.tsx`, `NoAccessPanel.tsx` since the prior report. `viewAccess`, `SidebarFailClosed`, `NoAccessScreens`, `catalogueAccess` tests re-run: pass. |
| 2 | A user with no permitted catalogue sees a clear no-access state with a guaranteed landing view and working Sign out | VERIFIED | Same files unchanged; `ZeroAccessScreen`, `landingView`, Retry and Sign out tests pass. |
| 3 | An admin sees, per role, which catalogues it can access, matching what the backend enforces | VERIFIED | `role_visibility.py` unchanged. `role_endpoints.py` changed only by the `_role_write` wrapper around the three writes (read endpoints untouched). `test_role_visibility`, `test_closure_delivery`, `test_role_routes_real_app` and `RoleVisibilityPanel.test.tsx` pass. |
| 4 | After an admin edits a role's permissions, the affected user's sidebar updates on next focus or 403, without re-login | VERIFIED | Front-end chain unchanged and traced in the previous report (403/focus/visibility -> `refreshPermissions` -> `currentUserRef` -> `setCurrentUser` -> `loadAllData`). The server side now also applies the edit to the MFA requirement at once (see below), so an edit that makes a role admin-tier no longer leaves a 60 s window in which the session is exempt. |
| 5 | Regression tests prove visibility and route guards hold per role and per tenant, including super-admin and `platform-admin`, and one tenant's role edit never changes another tenant's users | VERIFIED | `test_role_tenant_isolation`, `test_platform_roles`, `test_auth_mfa`, `test_role_literal_guard`, `viewAccess.test.ts` pass. New tests assert that invalidation drops only the named tenant (`test_invalidation_drops_only_the_named_tenant`; `test_role_writes_clear_the_tenants_cached_mfa_answers` keeps `tenant-b` cached). |

**Score:** 5/5 truths verified (0 present, behavior-unverified). Live-system behaviour is routed to human verification.

### D-14 permission-based MFA (77-04 must_haves), current code

| 77-04 must-have | Status | Evidence |
|---|---|---|
| MFA is permission-based; a session whose effective set holds `*` or an `ADMIN_TIER_PERMISSIONS` entry must pass MFA (403 `X-MFA-Required`) on every route that does not allow a pending session | VERIFIED | `rbac_defaults.requires_mfa` (line 186) is the only predicate. HTTP: `get_current_user` -> `verify_token_async` -> `resolve_mfa_required` -> `_enforce_admin_mfa(..., required)` raises 403 with `X-MFA-Required: 1` (authentication_service.py 444-445, 156-163). Skipped only for `allow_mfa_pending`, `mfa_verified` or agent payloads, as designed. |
| Admin-tier set defined once; built-in table selects the same roles as before | VERIFIED | `ADMIN_TIER_PERMISSIONS` only in `rbac_defaults.py` (177-183). `_mfa_table_answer` answers built-ins from the table with no lookup. `test_auth_mfa`, `test_platform_roles` (built-in matrix) pass. |
| Name-keyed role set removed; custom admin-tier role needs MFA, custom non-admin role does not | VERIFIED | No role-name set in `authentication_service.py`. Matrix tests in `test_custom_role_mfa.py` (Helpdesk False, Deskadmin True) pass. |
| Custom-role answer cached per (tenant, role) for 60 s per worker; a role edit is enforced without a new login | VERIFIED, strengthened | The 60 s TTL stays as the cross-worker bound. On the serving worker, `create_role`, `update_role` and `delete_role` each run their store write inside `_role_write(tenant_id)` (role_endpoints.py 176-183, 210, 260, 289) whose `finally` calls `invalidate_mfa_role_cache(tenant_id)`, so the next request re-reads the role. Order is correct: the invalidation runs after the write returns. The deployed backend is a single uvicorn process (`ps`: `uvicorn app:socket_app`, no `--workers`), so the serving worker is the whole backend today. |
| A lookup in flight during a role write cannot re-cache its pre-edit answer (IN-12) | VERIFIED | `resolve_mfa_required` snapshots `_mfa_cache_generation[tenant]` before the lookup and stores only if unchanged (lines 140-153); `invalidate_mfa_role_cache` bumps the generation and pops the tenant's entries. A lookup that finished before the write is cleared by the later `finally`; one that finishes after is dropped by the generation check; one that starts after the write reads post-edit data. `test_a_lookup_overtaken_by_a_role_write_is_not_cached` simulates the overtake and passes; `test_a_failed_create_after_the_insert_still_clears_the_cache` covers the failing-write path. The only other `roles` writer is startup seeding (app_startup.py:326), which runs with an empty cache. |
| Fail closed: store error requires MFA for a custom role; built-in uses the table answer | VERIFIED, refined | Custom name: `not builtin` is True. Built-in name: table answer, but now never less strict than the last cached answer (a tenant document can add `manage:users` to `viewer`), via `last = _mfa_role_cache.get(...)`. This reads the expired entry too, so it stays strict across a store outage. Logged at error level. Error answers are not cached. `test_store_error_never_answers_less_strictly_than_the_last_answer` passes. This is a deliberate tightening of the 77-04 wording ("built-in uses the table answer"), in the safe direction, and a cold-cache built-in with no prior answer still uses the table. |
| WebSocket path: table answer for built-ins, cached answer for custom names, cache miss = MFA required | VERIFIED, superseded | `websocket_manager.connect` now awaits `verify_token_async` (line 180), so on a cold cache it asks the role store like every HTTP route instead of guessing True for every custom role. The support-chat registration reuses `token_data` (lines 223-230) instead of verifying a second time. `connect` remains a rejected-connection (`return False`) on any raise, so an admin-tier custom role without MFA is refused. Tests: `test_websocket_connect_resolves_mfa_from_the_role_store` (Helpdesk connects, Deskadmin refused) and `test_websocket_connect_holds_an_extended_builtin_to_mfa` pass; the rate-limit test now patches both verifiers and still proves no token check happens before the limit. The synchronous `verify_token` has no remaining production caller (grep: only tests), so the old cold-cache misfire cannot recur through another route; it keeps the fail-closed rule (`mfa_required_for` returns `not builtin` on a miss). The flagged assumption D14-WS-CACHE-MISS (a socket reconnect after 60 s idle refused) is therefore closed. |
| `/api/auth/login` and `/me` report `mfa_action` for a custom admin-tier user as for built-in admin roles | VERIFIED | authentication_endpoints.py 243-244 and 289-291 pass `required=await resolve_mfa_required(...)` to `mfa_action_for`; `test_custom_role_mfa` mfa_action cases pass. |

Residual limits (not defects against the criteria; documented in code comments):
- Another worker would see an edit only after its own 60 s TTL. Not reachable with the current single-process deployment.
- Socket MFA is evaluated at connect only. A socket opened before an edit is not re-checked until it reconnects. HTTP routes are re-checked on every request.
- `/auth/me` stays reachable for a session that has just become MFA-pending (it uses the pending-allowed dependency), so the UI's permission refresh keeps working and the existing `omni:mfa-required` handler (apiService.ts 320, App.tsx 776-779) raises the enroll/verify gate; `fetchCurrentPermissions` returns null (keeps the last list) when `mfa_action` is present (apiService.ts 764).

### Deferred Items

None. Later milestone phases (78-80) cover cost work, not access.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/rbac_defaults.py` | `ADMIN_TIER_PERMISSIONS`, `requires_mfa` | VERIFIED | Single definition, used by the resolver |
| `backend/authentication_service.py` | `resolve_mfa_required`, `invalidate_mfa_role_cache`, generation guard, permission-based `_enforce_admin_mfa` | VERIFIED | Substantive; called from verify_token_async, login, /me, role_endpoints |
| `backend/role_endpoints.py` | Role CRUD with `_role_write` invalidation | VERIFIED | All three writes wrapped |
| `backend/websocket_manager.py` | Socket connect with the async token check | VERIFIED | Wired; second verify removed |
| `backend/tests/test_custom_role_mfa.py` | MFA matrix + new cache, socket tests | VERIFIED | passes |
| `utils/viewAccess.ts`, `NoAccessPanel.tsx`, `ZeroAccessScreen.tsx`, `permissionRefresh.ts`, `Sidebar.tsx`, `RoleVisibilityPanel.tsx`, `role_visibility.py` | As in the prior report | VERIFIED | Unchanged since f3a760ceb |

### Key Link Verification

| From | To | Via | Status |
|------|----|-----|--------|
| `role_endpoints` create/update/delete | `authentication_service._mfa_role_cache` | `_role_write` -> `invalidate_mfa_role_cache(tenant_id)` in `finally` | WIRED |
| `authentication_service.verify_token_async` | `resolve_mfa_required` | `_enforce_admin_mfa(..., required)` (skipped only for pending/verified/agent) | WIRED |
| `resolve_mfa_required` | `rbac_service.effective_permissions` | lazy import (circular import avoided), reads the tenant's role documents | WIRED |
| `websocket_manager.connect` | `verify_token_async` | `await`, one call, `token_data` reused for registration | WIRED |
| `authentication_endpoints` login and /me | `resolve_mfa_required` | `required=` argument of `mfa_action_for` | WIRED |
| Front-end links (403, focus, visibility -> `refreshPermissions` -> `loadAllData`; `Sidebar`/`ViewGate` -> `evaluateViewAccess`; `SettingsRolesTab` -> visibility) | | | WIRED, unchanged files |

### Data-Flow Trace (Level 4)

| Artifact | Data | Source | Real data | Status |
|----------|------|--------|-----------|--------|
| MFA requirement | `required` | `effective_permissions(db, role, tenant)` over the tenant's role documents | Yes (cache invalidated on each role write) | FLOWING |
| Sidebar / ViewGate / datasets after refresh | `currentUser.permissions` | `/login`, `/auth/me` | Yes | FLOWING (unchanged) |
| RoleVisibilityPanel | visibility payload | `GET /roles/{id}/visibility` -> `build_visibility` | Yes | FLOWING (unchanged) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| MFA matrix, cache invalidation, generation guard, store-error rule, socket connect, role write API, visibility, tenant isolation, closure, real-app routes, platform roles, auth MFA, role literal guard | `backend/venv/bin/python -m pytest -q` on test_custom_role_mfa, test_role_write_api, test_websocket_connect_rate_limit, test_role_visibility, test_role_tenant_isolation, test_closure_delivery, test_role_routes_real_app, test_auth_mfa, test_platform_roles, test_role_literal_guard | 359 passed | PASS |
| Gate, sidebar, refresh, visibility panel behaviours | `npx vitest run` on permissionRefresh, catalogueAccess, viewAccess, SidebarFailClosed, NoAccessScreens, RoleVisibilityPanel | 6 files, 121 passed | PASS |

Full-suite results (backend 4050 passed / 47 skipped, vitest 420 passed in 44 files) are the orchestrator's; I did not re-run the full suites.

### Probe Execution

Step 7c: SKIPPED (no probes declared by this phase's plans).

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|--------------|-------------|--------|----------|
| ACC-06 | 77-01, 77-02, 77-05, 77-08, 77-13 | Fail-closed sidebar, render-time gate, no-access / zero-access state | SATISFIED | Truths 1, 2 |
| ACC-07 | 77-07, 77-09 | Admin "what can this role see" view | SATISFIED | Truth 3 |
| ACC-08 | 77-03, 77-05, 77-11, 77-12 | Refresh permissions on 403 and window focus; edit takes effect without re-login | SATISFIED | Truth 4, plus the MFA requirement now follows the edit at once |
| ACC-09 | 77-01, 77-03, 77-04, 77-06, 77-07, 77-10, 77-12 | Regression tests per role, tenant, super-admin / platform-admin (incl. permission-based MFA, D-14) | SATISFIED | Truth 5; D-14 table above |

All four IDs appear in PLAN frontmatter and in REQUIREMENTS.md (lines 16-19, traceability 66-69); no orphaned requirements for Phase 77.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `backend/authentication_service.py` | 85 | `_clear_mfa_role_cache` clears the entries but not the generation map | Info | Test helper only; the generation map is an int counter per tenant, so no leak that matters |
| `backend/role_endpoints.py` | n/a | WR-04, WR-05, WR-07, IN-01..06 open in `77-REVIEW-DISPOSITION.md` | Warning / Info | None breaks a roadmap criterion |
| `utils/viewAccess.ts` | resolveHashView | WR-06 inherited `Object.prototype` hash names | Warning | Fails closed |
| `App.tsx` | 473 | No load sequence token (IN-08) | Warning | Narrow dataset-freshness window, sidebar/gate unaffected |
| `services/apiService.ts` | authFetch | WR-11, pre-existing June 2026 authFetch behaviour, outside this phase | Info | Not introduced by Phase 77 |

Review state: 24 findings in `77-REVIEW.md` (0 critical, 11 warning, 13 info). WR-01, 02, 03, 08, 09, 10, IN-09 and IN-12 are fixed (reviewer confirmed WR-02, WR-03, WR-10, IN-12). No unreferenced TBD/FIXME/XXX in the changed backend files (grep of `authentication_service.py`, `role_endpoints.py`, `websocket_manager.py` finds none). The working tree shows no uncommitted content changes in the phase's implementation files (`utils/catalogueAccess.ts` and `utils/permissions.ts` show only a file-mode change, 644 to 755).

### Human Verification Required

1. **Two-session role edit refresh.** Deploy, edit a role (add then remove a catalogue permission), focus or trigger a 403 in the other session. Expected: sidebar updates without re-login, new catalogue data loads at once, removal swaps the open screen to the no-access panel.
2. **Restricted roles on the live system.** itam_viewer and a zero-screen custom role walk the sidebar, hashes and chat navigation. Expected: forbidden items absent, in-place panel on deep links, zero-access screen with Retry and Sign out, no raw 403 toasts.
3. **Layout at 320/375/768 px, light and dark.** No horizontal scroll; action row stacks under 400 px.
4. **Super Admin visibility panel vs. actual sidebar.** Per-role lists match what holders see.
5. **New this round: MFA follows a role edit on HTTP and on the socket.** After the restart, add `manage:users` to a custom role held by a user with an open session and no MFA. Expected: the next API call gets the MFA gate at once (not after 60 s), a fresh socket connect is refused until MFA, removal lifts it. Why human: the running backend still holds the old code, and the deployed wiring (UI edit -> `_role_write` -> cache -> gate) is covered by unit tests only.

### Gaps Summary

No roadmap success criterion failed and no gap is open. The D-14 truths hold on both paths: HTTP routes and the socket connect resolve the MFA requirement from the role store through the same `resolve_mfa_required`, a role write on the serving worker clears the tenant's cached answers and a generation guard stops an overtaken lookup from restoring the old answer, so an edit that makes a role admin-tier takes effect on the next request without a re-login (single-process deployment; other workers lag by at most 60 s). The one deviation from the 77-04 wording (a store error on a built-in name never answers below the last known answer) is a safe tightening. Truths 1, 2, 3 and 5 did not regress: the front-end files are unchanged and their tests pass. Status stays `human_needed` because five checks need the deployed system or visual inspection (backend not restarted, UI bundle not published). Remaining open review items (WR-04..07, WR-11, IN-01..08, IN-10, IN-11, IN-13) are warnings and info outside the five criteria.

---

_Verified: 2026-10-19 (re-verification)_
_Verifier: Claude (gsd-verifier)_
