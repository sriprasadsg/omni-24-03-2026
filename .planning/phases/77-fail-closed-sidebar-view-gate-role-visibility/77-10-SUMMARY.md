---
phase: 77-fail-closed-sidebar-view-gate-role-visibility
plan: 10
subsystem: auth
tags: [rbac, tenant-isolation, regression-tests, super-admin, mfa, real-app-probe]
requires:
  - phase: 77-03
    provides: role write API (role_endpoints)
  - phase: 77-04
    provides: permission-keyed MFA
  - phase: 77-06
    provides: custom role assignment
  - phase: 77-07
    provides: GET /api/roles/{id}/visibility
provides:
  - backend/tests/test_role_tenant_isolation.py (SC5 cross-tenant isolation, per-tenant visibility, super-admin spellings)
  - backend/tests/test_role_routes_real_app.py (15-case real-app guard sample)
affects: [77-11, 77-12]
status: complete
plan_head_before: 6a514cfce1b3f3f32b3679679e630bf274bdfe26
plan_head_after: ab0f11c02c78ffa218f144f6fe71c38b97609479
actuals:
  tokens: 6000
  tasks: 2
  commits: 2
tech-stack:
  added: []
  patterns:
    - "one in-memory role store shared by the role app and the auth app (make_auth_client) to prove a write changes /me for one tenant only"
key-files:
  created:
    - backend/tests/test_role_tenant_isolation.py
    - backend/tests/test_role_routes_real_app.py
  modified: []
key-decisions:
  - "Test-only plan: every case passed on first run against the 77-01..77-07 modules (characterization), so no fix commits were needed"
  - "ACC-09 left unchecked: requirements.ready-ids reported 0/1 ready (the ID is shared with 77-11/77-12)"
requirements-completed: []
---

# Phase 77 Plan 10: Tenant isolation and real-app role route regression Summary

Role-edit isolation between tenants, per-tenant visibility, every super-admin spelling and the role route guards on the production registry are now pinned by tests; the full backend suite is green.

## Task 1 (tracer): test_role_tenant_isolation.py (15 test cases, 8 named tests)

- `test_tenant_a_edit_never_changes_tenant_b`: both tenants hold a custom "Helpdesk" (A `view:agents`, B `view:logs`); tenant A's admin adds `view:security`; A's holder gains it on the next `/api/auth/me`, B's `/me` response is byte-identical.
- `test_cross_tenant_role_ids_are_404`, `test_foreign_tenant_id_is_refused` (403), `test_sentinel_catalogues_are_unreachable` ("all"/"platform": 403 for a tenant admin, 400 for a Super Admin; PUT/DELETE on `role-viewer` 404).
- `test_visibility_follows_each_tenants_switches` (real tenant features): the compliance screens are switched off for A and visible for B; an edit in A leaves B's visibility payload equal.
- `test_every_super_admin_spelling_is_wildcard` (5 spellings): `["*"]`, `verify_permission` true for any permission, and GET `/api/roles` lists Platform Support and Platform Billing.
- `test_platform_roles_are_never_narrowed` (per platform role): granted equals the closed effective set under a two-entry enabledFeatures list, no `screen-off:` markers.
- `test_custom_role_mfa_is_per_tenant`: after A's Helpdesk gains `manage:rbac`, A's holder is told to enroll and B's same-named holder is not.

## Task 2: test_role_routes_real_app.py

One `probe_real_app` call, 15 cases: viewer and itam_admin refused (403) on POST; viewer refused on permission-catalogue, visibility, PUT, DELETE; tenant_admin admitted past the guard on POST, catalogue, visibility; itam_admin admitted on visibility; super_admin (tenant platform-admin) admitted on POST, PUT, DELETE, catalogue, visibility. Per-case assertion messages name method, path, role and status.

## Verification

- Task 1 set (isolation, write API, visibility, assignment, MFA, closure delivery): 250 passed. `shared/` untouched by the run (its only status entry is a pre-existing mode-only change with an unchanged mtime).
- Task 2 module: 1 passed in about 7 s. The parity modules (route parity, billing/identity slice, audit parity) run inside the full suite.
- Full backend suite: **4043 passed, 47 skipped** (baseline after 77-07: 4027 / 47; +15 isolation tests +1 real-app test; original phase baseline 3780 / 47), 698 s.

## Deviations from Plan

None. One test-authoring correction: the visibility test first narrowed tenant A's switches before creating a role and so lost `manage:rbac` (403); the role is now created before the switches change. The assertions were not weakened.

## Known Stubs

None.

## Threat Flags

None. The plan adds tests only; no live database, ledger or shared file is written (in-memory store, fake audit recorder, throwaway probe environment).

## Self-Check: PASSED

- backend/tests/test_role_tenant_isolation.py: FOUND (commit 884199112)
- backend/tests/test_role_routes_real_app.py: FOUND (commit ab0f11c02)
