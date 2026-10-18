---
phase: 77-fail-closed-sidebar-view-gate-role-visibility
plan: 01
subsystem: auth
tags: [rbac, permissions, tenant-feature-switches, closure, sidebar]
requires:
  - phase: 75
    provides: single role table (rbac_defaults), shared resolver (rbac_service), /login and /me delivery
  - phase: 76
    provides: catalogue-access manifest and tenant-feature switch catalogue
provides:
  - permission_vocabulary.KNOWN_PERMISSIONS (derived known-permission set)
  - rbac_defaults.deliverable_closure (manage:X => view:X/request:X, vocabulary-filtered)
  - closure applied once in granted_permissions and _fallback_permissions (enforcement == delivery)
  - tenant_features.NAV_SCREENS, NAV_GROUPS, switched_off_nav_screens, apply_tenant
  - D-16 screen-off:<view> markers for every nav screen a role grants but the tenant switched off
affects: [77-02, 77-07, sidebar, role visibility view]
status: complete
plan_head_before: b38314178c3c820c222f5df214e8d30d8f23b970
plan_head_after: 467f61c434ea85472f57109ab4f5ba7b812fdf74
actuals:
  tokens: 6300
  tasks: 2
  commits: 2
tech-stack:
  added: []
  patterns:
    - "one closure rule shared by ceiling_allows and delivery (implied_closure)"
    - "tenant narrowing and marker emission in one step (apply_tenant)"
key-files:
  created:
    - backend/permission_vocabulary.py
    - backend/tests/test_closure_delivery.py
  modified:
    - backend/rbac_defaults.py
    - backend/rbac_service.py
    - backend/tenant_features.py
    - backend/tests/test_login_me_permissions.py
    - backend/tests/test_effective_permissions.py
    - backend/tests/test_tenant_feature_switches.py
key-decisions:
  - "Closure lives in granted_permissions/_fallback_permissions before tenant narrowing; effective_permissions stays un-closed (role definition, assignment ceiling)"
  - "Closure filtered to KNOWN_PERMISSIONS (139 strings) instead of the raw implied_closure (A1)"
requirements-completed: [ACC-06, ACC-09]
---

# Phase 77 Plan 01: Closure and switched-off markers Summary

The D-11 closure (manage:X implies view:X and request:X, filtered to known strings) now runs once in the resolver that backs both `verify_permission` and `/login`/`/me`, and every nav screen a role grants but its tenant switched off carries a `screen-off:<view>` marker (D-16).

## Accomplishments

- **Task 1 (tracer), commit c4b63ec15:** `permission_vocabulary.KNOWN_PERMISSIONS` (derived by set union over the role table, platform/super-admin sets, manifest permission/read/write and the switch catalogue; no literal list), `rbac_defaults.deliverable_closure`, and the closure inside `granted_permissions` and `_fallback_permissions`, ahead of the tenant narrowing. Platform roles get the closure but are still never narrowed.
- **Task 2, commit 467f61c43:** `tenant_features.NAV_SCREENS` (188), `NAV_GROUPS` (8), `switched_off_nav_screens`, and `apply_tenant`, which replaces the inline narrow plus `hidden_screens` pair in both resolver paths and de-duplicates markers in first-seen order.

## itam_admin delivered list

Before: `manage:assets, manage:finance, manage:itam, manage:licenses, manage:procurement, manage:users, view:itam, view:profile`

After: the same eight, followed by `request:assets, view:assets, view:licenses`. Assets (assetManagement) and Certificates now resolve for it, and `verify_permission(itam_admin, "request:assets")` is True with `backend/itam_asset_request_endpoints.py` untouched. itam_user, itam_viewer and tenant_admin lists are unchanged; no other built-in role gained anything.

## Existing tests updated

| Test | Change | Citation |
|------|--------|----------|
| test_login_me_permissions.py `ITAM_EXPECTED["itam_admin"]` and `test_itam_role_gets_real_permissions_from_login_and_me` | closed list; now asserts view:assets delivered | D-11 |
| test_login_me_permissions.py `test_login_equals_me_for_every_builtin_role` | itam_admin compares to the closed list, other roles to the table | D-11 |
| test_effective_permissions.py `test_verify_permission_matches_resolver_for_every_builtin_role` | delivery side is `granted_permissions` (enforcement and delivery both closed), table subset still asserted against `effective_permissions` | D-11 |
| test_tenant_feature_switches.py `test_granted_permissions_mark_the_switched_off_screens` | `screen-off:compliance` now present while `view:compliance` is absent; other assertions kept | D-16 |

## Verification

- Plan verify sets: Task 1 set 105 passed; Task 2 role test set (test_closure_delivery, test_tenant_feature_switches, test_login_me_permissions, test_effective_permissions, test_roles_endpoint, test_role_assignment_ceiling, test_catalogue_guards, test_platform_roles, test_rbac_defaults) 492 passed.
- Full backend suite: 3812 passed, 47 skipped (baseline 3780 / 47; +32 new tests).
- Acceptance greps: `def deliverable_closure` 1, `deliverable_closure(` in rbac_service 2, `def apply_tenant` 1, `apply_tenant(` in rbac_service 2, NAV_SCREENS 188 / NAV_GROUPS 8, `itam_asset_request_endpoints.py` untouched, drift guard `test_no_second_permission_table` green.
- Tracer gate (interactive, end-of-phase, automated-only verify): the verify command was re-run end to end after Task 1 and passed, so Task 2 proceeded.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Test pin] test_effective_permissions parity test compared enforcement to the un-closed set**
- **Found during:** Task 1 regression run
- **Issue:** `test_verify_permission_matches_resolver_for_every_builtin_role[itam_admin]` failed because verify_permission now (intentionally, D-11/A8) grants request:assets that effective_permissions does not list.
- **Fix:** compare against `granted_permissions` (the shared resolver); keep the table-subset assertion on `effective_permissions`.
- **Files modified:** backend/tests/test_effective_permissions.py
- **Commit:** c4b63ec15

**2. [Rule 3 - Task split] D-16 tests held back from Task 1's commit**
- The D-16 marker tests were drafted in the same new test file but committed with Task 2, so each commit stays green on its own verify command.

Otherwise the plan was executed as written. Both flagged assumptions (A1 vocabulary filter, A8 strict checks widen for manage:X holders) are implemented as stated; no refusal-pinning test other than the one above needed changing.

## Known Stubs

None.

## Threat Flags

None. No new endpoints, auth paths or schema; T-77-01 and T-77-02 mitigated by tests (no control:/manage: derivation, unknown strings dropped, closure before narrowing with switched-off assets removed and marked).

## Self-Check: PASSED

- Files exist: permission_vocabulary.py, test_closure_delivery.py, SUMMARY.
- Commits c4b63ec15 and 467f61c43 are ancestors of HEAD.
