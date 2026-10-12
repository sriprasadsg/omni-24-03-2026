---
phase: 75-permission-resolver-single-source-of-truth
plan: 02
subsystem: auth
tags: [rbac, permissions, seeding, mongodb, tenant-isolation, pytest]
status: complete

requires:
  - phase: 75-01
    provides: rbac_defaults.seed_role_documents, rbac_service.session_permissions, tests/rbac_test_support
provides:
  - one startup seed loop mirroring the table into 11 shared role documents through the raw roles handle
  - signup without a stored permissions array, response permissions from session_permissions
  - POST /api/mfa/verify response carrying resolver permissions
affects: [75-03, 75-04 role assignment ceiling, 75-05 drift test, 77 /me consumer]

plan_head_before: 75ec039b08d8bf866d78633c9abe1468923548eb
plan_head_after: f2512798770826d2c107c1dbab71a1e1df3d0793

actuals:
  tokens: 9000
  tasks: 2
  commits: 4

tech-stack:
  added: []
  patterns:
    - "Seed through db._db.roles with a {name, tenantId} filter so the platform-admin wrapper bypass cannot reach tenant-scoped documents"
    - "Per-document try/except in a seed loop (ARCH-018)"

key-files:
  created:
    - backend/tests/test_role_seeding.py
  modified:
    - backend/app_startup.py
    - backend/authentication_endpoints.py
    - backend/mfa_endpoints.py
    - backend/tests/test_seed_database_step_isolation.py
    - backend/tests/test_login_me_permissions.py

key-decisions:
  - "The seed step wraps the whole loop in an outer try/except as well as one per document, so a failure of the step itself (for example reading db._db) is still logged by step name"
  - "The original test_seed_database_step_isolation tests were kept (rewired to the raw handle) rather than replaced; the real-wrapper behaviour lives in the new test_role_seeding.py"

requirements-completed: [ACC-01, ACC-02]

coverage:
  - id: D1
    description: "After seed_database() the 11 shared role documents exist (itam_admin, itam_user, itam_viewer, admin included; Super Admin at tenantId platform with [*]) and equal the table; two runs leave 11"
    requirement: "ACC-02"
    verification:
      - kind: integration
        ref: "backend/tests/test_role_seeding.py#test_seeds_eleven_shared_documents_and_leaves_tenant_document_untouched"
        status: pass
      - kind: integration
        ref: "backend/tests/test_role_seeding.py#test_seeding_twice_is_idempotent"
        status: pass
    human_judgment: false
  - id: D2
    description: "A tenant-scoped role document with the same name is never matched, modified or relabelled by seeding"
    requirement: "ACC-02"
    verification:
      - kind: integration
        ref: "backend/tests/test_role_seeding.py#test_seeds_eleven_shared_documents_and_leaves_tenant_document_untouched"
        status: pass
      - kind: integration
        ref: "backend/tests/test_role_seeding.py#test_seeding_without_tenant_context_still_writes_all_documents"
        status: pass
    human_judgment: false
  - id: D3
    description: "Manual edits to shared documents (96-string Super Admin list, manage:tenants on Tenant Admin) are reverted on the next startup; a single failed write does not block the others or the ITAM backfill"
    requirement: "ACC-02"
    verification:
      - kind: integration
        ref: "backend/tests/test_role_seeding.py#test_live_shaped_super_admin_updated_in_place"
        status: pass
      - kind: integration
        ref: "backend/tests/test_role_seeding.py#test_manual_edit_of_shared_document_is_reverted"
        status: pass
      - kind: integration
        ref: "backend/tests/test_role_seeding.py#test_one_failed_document_does_not_stop_others_or_itam_backfill"
        status: pass
    human_judgment: false
  - id: D4
    description: "Signup and MFA verify-login responses carry user.permissions from session_permissions, equal to /me; signup stores no permissions array and a stale stored array never reaches a response"
    requirement: "ACC-01"
    verification:
      - kind: integration
        ref: "backend/tests/test_login_me_permissions.py#test_signup_response_carries_resolver_permissions"
        status: pass
      - kind: integration
        ref: "backend/tests/test_login_me_permissions.py#test_signup_permissions_match_me"
        status: pass
      - kind: integration
        ref: "backend/tests/test_login_me_permissions.py#test_mfa_verify_carries_resolver_permissions"
        status: pass
      - kind: integration
        ref: "backend/tests/test_login_me_permissions.py#test_mfa_verify_ignores_stored_permissions"
        status: pass
    human_judgment: false
  - id: D5
    description: "After the user restarts the backend, a read-only query of the live roles collection shows 10 documents at tenantId all plus Super Admin at tenantId platform with [*], with tenant-scoped role documents unchanged"
    requirement: "ACC-02"
    verification: []
    human_judgment: true
    rationale: "Live database is off-limits during execution and the restart is user-owned (75-VALIDATION.md Manual-Only)"

duration: 25 min
completed: 2026-10-12
---

# Phase 75 Plan 02: Startup Seed Mirror and Signup/MFA Permissions Summary

**Startup now mirrors `rbac_defaults` into all 11 shared role documents (ITAM roles and `admin` included) through the raw roles handle with a `{name, tenantId}` filter, and signup plus MFA verify-login deliver the resolver's permissions.**

## Performance

- **Duration:** about 25 min
- **Tasks:** 2 of 2 (both TDD: RED then GREEN)
- **Files:** 1 created, 5 modified

## Accomplishments

- `backend/app_startup.py` 834 to 656 lines: the Super Admin, Tenant Admin and standard-roles blocks (three copies of the truth) are replaced by one step that iterates `seed_role_documents()` and calls `db._db.roles.update_one({"name", "tenantId"}, {"$set": doc}, upsert=True)` per document, each in its own try/except that logs the role name. Super Admin keeps tenantId `platform` and now stores `["*"]` instead of the 96-string list. The super admin user step, platform tenant step and ITAM enabledFeatures backfill are untouched and in the same order. The docstring step list is updated.
- `backend/tests/test_role_seeding.py` (7 tests) runs the real `seed_database()` over the real `TenantIsolatedDatabase` inside a fresh `contextvars.Context` with the platform-admin tenant set: 11 documents with tenant `viewer` document byte-for-byte unchanged, documents equal the table, idempotent, live-shaped Super Admin updated in place with no duplicate at `all`, stale Tenant Admin reverted, works with no tenant context, one failing write leaves the other 10 and the ITAM backfill intact.
- `test_seed_database_step_isolation.py` rewired to `db._db.roles.update_one` and the 11-name expectation.
- `authentication_endpoints.signup`: the 63-entry permission literal and the stored `permissions` key are gone (D-07); the response sets `user.permissions` from `session_permissions(db, "Tenant Admin", tenant_id)`. The tenant tier list `free_features` is deliberately untouched.
- `mfa_endpoints.verify_mfa_at_login`: response `user.permissions` from `session_permissions(db, role, tenant_id)` (D-24).

## Task Commits

1. **Task 1 RED: failing seeding tests** - `498ff22b4` (test)
2. **Task 1 GREEN: single seed loop, step-isolation tests rewired** - `b33733287` (feat)
3. **Task 2 RED: failing signup/MFA tests** - `d4dbf6040` (test)
4. **Task 2 GREEN: signup and MFA verify deliver resolver permissions** - `f25127987` (feat)

### TDD Gate Compliance

- Task 1 RED: `test_role_seeding.py` (7 tests) failed on the planned assertions (shared-document count and contents, tenant-document untouched, Super Admin `["*"]`); the old code only wrote 7 names, left Super Admin with the 96-string list and, with no tenant context, matched nothing. semanticAssessment: target tests collected and executed, failed for the intended behavioural reasons (not import or fixture faults). The format-based `gsd_run check tdd-red-evidence` classifier was not run (pytest short report is not one of its supported formats); RED was inspected manually from the pytest output.
- Task 2 RED: the 4 `-k "mfa or signup"` tests failed on the planned assertions (signup returned the stored 63-entry list rather than the table; MFA response had no `permissions` key / returned the stale stored array). Same manual classification.
- GREEN commits followed their RED commits; no refactor commits were needed.

## Verification

- `pytest test_role_seeding.py test_seed_database_step_isolation.py -q`: 11 passed (7 + 4).
- `pytest test_login_me_permissions.py -k "mfa or signup"`: 4 selected, 4 passed.
- `pytest test_login_me_permissions.py test_auth_mfa.py test_admin_mfa_required.py test_session_revocation.py test_role_seeding.py test_seed_database_step_isolation.py`: 142 passed.
- Full backend suite (`backend/venv/bin/python -m pytest tests`): 2994 passed, 47 skipped, 0 failed (previous 2951 plus 43 from 75-01's later additions and this plan's 11 new tests).
- Acceptance greps: name-only role filter count 0 (was 3); `seed_role_documents()` count 1; `tenant_admin_permissions|all_permissions|standard_roles` 0; `roles.update_one` 1; `enterprise_permissions` 0; `session_permissions(` 3 in authentication_endpoints, 1 in mfa_endpoints; `"permissions":` 0 in authentication_endpoints; `app_startup.py` 656 lines (< 834).

## Deviations from Plan

None - plan executed exactly as written.

## Pre-existing working-tree changes included

- `backend/tests/test_seed_database_step_isolation.py` carried an uncommitted 3-line hunk from earlier unrelated work (`import sys, os` split into two import lines); it was staged with the file in the Task 1 GREEN commit. `backend/app_startup.py`, `backend/mfa_endpoints.py` and `backend/authentication_endpoints.py` were clean at start (committed by the orchestrator before dispatch).

## Authentication Gates

None.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register. T-75-06 (seed upsert scoped by `{name, tenantId}`) and T-75-07 (stale shared documents reverted each boot) are covered by `test_role_seeding.py`; T-75-08 by `test_signup_response_carries_resolver_permissions` and `test_mfa_verify_ignores_stored_permissions`.

## Issues Encountered

None. Live system untouched: no restarts, deploys or writes to `omni_platform`; all seeding ran against in-memory fakes. The live roles collection will only be reseeded when the user restarts the backend.

## Next Phase Readiness

Ready for 75-03. Operational note for the user: on the next backend restart the live `roles` collection gains `admin`, `itam_admin`, `itam_user`, `itam_viewer` shared documents, the Super Admin document shrinks to `["*"]`, and shared documents reset to the table (manual edits to them are reverted). Tenant-scoped role documents are not touched.

## Self-Check: PASSED

- Files: backend/tests/test_role_seeding.py, backend/app_startup.py, backend/authentication_endpoints.py, backend/mfa_endpoints.py, backend/tests/test_login_me_permissions.py, backend/tests/test_seed_database_step_isolation.py present.
- Commits 498ff22b4, b33733287, d4dbf6040, f25127987 are ancestors of HEAD.
