---
phase: 75-permission-resolver-single-source-of-truth
plan: 01
subsystem: auth
tags: [rbac, permissions, fastapi, tenant-isolation, pytest]
status: complete

requires:
  - phase: 74-remote-access-control
    provides: view:remote_access and control:remote_access as independent permissions (D-06)
provides:
  - backend/rbac_defaults.py, the only role-to-permission table, with built-in role metadata and pure helpers
  - rbac_service.effective_permissions and session_permissions, the one resolver for delivery and enforcement
  - /login and /me delivering the same server-evaluated permission list for every built-in role
  - verify_permission, RBACService.get_user_permissions, get_permissions_for_role and can_assign_role answering from the table
  - tests/rbac_test_support.py in-memory role/user store over the real TenantIsolatedDatabase
affects: [75-02 seed mirror and signup, 75-03, 75-04 role assignment ceiling, 75-05 drift test, 76 manifest, 77 /me consumer]

plan_head_before: ebec77d512f80390b16e28bc2c8fb517e5dba98a
plan_head_after: b68bad56d79ae68a592d69e3e85eb267e0771ff1

actuals:
  tokens: 15000
  tasks: 3
  commits: 4

tech-stack:
  added: []
  patterns:
    - "Single table + single async resolver; enforcement and delivery both call it"
    - "Raw db._db handle with explicit tenantId (own tenant, all, platform) for role documents so public-path /login sees tenant-scoped documents"
    - "Defaults-first, document-extras-after, first-seen de-duplicated ordering for stable lists"

key-files:
  created:
    - backend/rbac_defaults.py
    - backend/tests/rbac_test_support.py
    - backend/tests/test_login_me_permissions.py
    - backend/tests/test_effective_permissions.py
    - backend/tests/test_rbac_defaults.py
  modified:
    - backend/rbac_service.py
    - backend/rbac_utils.py
    - backend/authentication_endpoints.py
    - backend/tests/test_rbac.py

key-decisions:
  - "effective_permissions lives in rbac_service (owns _normalize_role); rbac_defaults is stdlib-only to avoid the rbac_utils -> rbac_service -> database import cycle"
  - "find_role_doc left untouched (zero_trust_service and test_find_role_doc depend on its wrapper call); a new raw-handle helper _role_docs does the resolver reads"
  - "verify_permission keeps a no-DB fast path on table defaults and fails closed when the role store raises; session_permissions and get_user_permissions degrade to table defaults only"
  - "RBACService.default_roles is a derived read-only dict (builtin keys plus legacy display key 'Tenant Admin') for user_endpoints, ldap/saml role validation and test_prod_hardening"
  - "can_assign_role is the table-only D-20 rule; tenant-scoped documents and the self-change rule are Plan 04"

patterns-established:
  - "Golden-set tests encode expected per-role permissions as literals so any table edit is a reviewable gained/lost failure"

requirements-completed: [ACC-01, ACC-02]

coverage:
  - id: D1
    description: "ITAM roles (itam_admin, itam_user, itam_viewer) receive a non-empty permission list from POST /api/auth/login and GET /api/auth/me"
    requirement: "ACC-01"
    verification:
      - kind: integration
        ref: "backend/tests/test_login_me_permissions.py#test_itam_role_gets_real_permissions_from_login_and_me"
        status: pass
    human_judgment: false
  - id: D2
    description: "/login and /me return the identical list for every built-in role, with and without role documents, and tenant-scoped documents extend both only for their own tenant"
    requirement: "ACC-01"
    verification:
      - kind: integration
        ref: "backend/tests/test_login_me_permissions.py#test_login_equals_me_for_every_builtin_role"
        status: pass
      - kind: integration
        ref: "backend/tests/test_login_me_permissions.py#test_tenant_scoped_document_extends_both_endpoints_for_own_tenant_only"
        status: pass
    human_judgment: false
  - id: D3
    description: "verify_permission, RBACService and delivery answer from one resolver; no second role-to-permission literal remains in rbac_utils or rbac_service"
    requirement: "ACC-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_effective_permissions.py#test_verify_permission_matches_resolver_for_every_builtin_role"
        status: pass
      - kind: command
        ref: "cat backend/rbac_utils.py backend/rbac_service.py | grep -cE '\"(admin|Tenant Admin|...)\": \\[' prints 0"
        status: pass
    human_judgment: false
  - id: D4
    description: "Exact per-role permission sets and table invariants (D-01..D-13, D-21, Phase 74 D-06) pinned by golden tests"
    requirement: "ACC-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_rbac_defaults.py"
        status: pass
    human_judgment: false

duration: 55 min
completed: 2026-10-12
---

# Phase 75 Plan 01: Permission Resolver Single Source of Truth Summary

**One role-to-permission table (`rbac_defaults.py`) and one async resolver (`effective_permissions`) now back `/login`, `/me`, `verify_permission` and `RBACService`, so an ITAM user logs in with a real permission list instead of `[]`.**

## Performance

- **Duration:** about 55 min
- **Tasks:** 3 of 3
- **Files:** 5 created, 4 modified

## Accomplishments

- `backend/rbac_defaults.py` (225 lines, stdlib only): `ROLE_DEFAULTS` for nine keys (127/22/19/17/12/8/8/5/4 permissions), `admin` alias, `SUPER_ADMIN_ONLY_PERMISSIONS` (manage:tenants plus the six D-03 catalogues), `BUILTIN_ROLES`, `defaults_for`, `canonical_key`, `builtin_role_keys`, `seed_role_documents`, `implied_closure`, `ceiling_allows`. The table content was generated from the three old literals with the Appendix A generator (extended for D-21 and `manage:itam` on `itam_admin`) and matched the plan's Target sets exactly before it was written.
- `rbac_service.effective_permissions`: super-admin variants resolve to `["*"]`; otherwise table defaults followed by document extras (own tenant, then `all`, then `platform`) read through `db._db` with an explicit tenantId, de-duplicated in first-seen order. `session_permissions` wraps it for delivery, degrades to defaults on a role-store error and logs a warning naming a role that resolves to nothing (D-19).
- `/login` and `/me` call `session_permissions`; the stale DB-F10 lookup blocks are gone. `/login` has no tenant context (public path) and still sees tenant-scoped documents.
- `verify_permission` (119 lines now) checks table defaults first with no DB hit, then `effective_permissions`, and still fails closed when the role store raises. The inner table and the `_CANONICAL_KEY_BY_NORMALIZED` redirect are deleted.
- `RBACService.default_roles` is derived from the table; `get_permissions_for_role`, `get_user_permissions` and `can_assign_role` read the table (D-20 ceiling with manage:X implying view:X and request:X). Tenant admins can no longer pass `manage:tenants`; `tenant_admin` (snake case) now resolves a full set instead of `[]`.

## Task Commits

1. **Task 1 (tracer): table, resolver, /login and /me** - `b07b49735` (feat)
2. **Task 2 RED: failing enforcement-parity tests** - `c52884d90` (test)
3. **Task 2 GREEN: enforcement through the shared resolver, old tables deleted** - `416e73510` (feat)
4. **Task 3: golden per-role sets and invariants** - `b68bad56d` (test)

Tracer gate: the tracer's `<verify>` (36 end-to-end tests plus the table sanity command) passed before expansion; no `blocking-human` gate was set.

## Verification

- `pytest backend/tests/test_login_me_permissions.py` 36 passed; `test_effective_permissions.py` 37 passed; `test_rbac_defaults.py` 32 passed (all above the plan minimums of 18, 15 and 12).
- Phase-affected suite (Task 2 second verify): 415 passed, 1 skipped, 0 failed.
- Full backend suite: 2951 passed, 47 skipped, 0 failed (baseline 2878 passed / 47 skipped; the delta is the new tests).
- Table sanity command prints `127 127 [22, 19, 17, 12, 8, 8, 5, 4] 11`; role-literal grep prints 0; `_CANONICAL_KEY_BY_NORMALIZED` count 0; `rbac_defaults.py` imports no database/fastapi/rbac_service/rbac_utils.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Plan behaviour text asked every ITAM role to contain view:assets**
- **Found during:** Task 1 (RED run)
- **Issue:** the behaviour bullet says each ITAM list contains `view:assets`, but the plan's own Target sets give `itam_admin` no `view:assets` (it holds `manage:assets`; D-10 keeps `view:assets` only where the role had it).
- **Fix:** the test asserts `manage:assets` for `itam_admin` and `view:assets` for `itam_user` and `itam_viewer`. The table follows the Target sets exactly.
- **Files modified:** backend/tests/test_login_me_permissions.py
- **Commit:** b07b49735

**2. [Rule 3 - Blocking] Acceptance grep for the raw-handle helper**
- **Found during:** Task 1
- **Issue:** `grep -c '_db.roles.find_one'` must reach 3; a local `raw_roles` alias would have made it 2.
- **Fix:** the helper calls `db._db.roles.find_one` directly.
- **Commit:** b07b49735

**Total deviations:** 2 auto-fixed (1 test-assertion correction, 1 style). **Impact:** none on behaviour or the table.

## Pre-existing working-tree changes included

The orchestrator committed the previously dirty target files as `ebec77d51` before dispatch, so `backend/authentication_endpoints.py` started clean and no unrelated hunks rode along in any task commit.

## Per-role diff vs. the plan table

Implemented as specified: `Tenant Admin` and `admin` both 127 (no `manage:tenants`, no D-03 catalogues); `user` 22, `analyst` 19, `security_analyst` 17, `incident_responder` 12, `viewer` 8 unchanged; ITAM roles gain `view:profile`, `itam_admin` also `manage:itam`; super-admin variants deliver `["*"]`.

## Known Stubs

None.

## Threat Flags

None beyond the plan's threat register. T-75-01..05 mitigations are in place and covered by `test_verify_permission_matches_resolver_for_every_builtin_role`, `test_other_tenants_document_never_contributes`, the three outage tests, `test_role_without_permissions_still_logs_in_and_warns` and the `test_rbac_defaults.py` D-03/D-06 invariants.

## Issues Encountered

None. Flagged assumption carried forward unchanged: a tenant-scoped document named `Tenant Admin` does not extend users whose role is `admin` (and vice versa).

## Next Plan Readiness

Ready for 75-02 (seed loop over `seed_role_documents()`, signup list). `RBACService.default_roles`, `user_endpoints._VALID_ROLE_KEYS` and the ldap/saml `valid_roles` keep working through the derived dict. Live system untouched: no service restarts, deploys or writes to `omni_platform`; the old seeded role documents in the live database are unchanged until Plan 02 reseeds on next boot.

## Self-Check: PASSED

- Files: backend/rbac_defaults.py, backend/tests/rbac_test_support.py, backend/tests/test_login_me_permissions.py, backend/tests/test_effective_permissions.py, backend/tests/test_rbac_defaults.py all present.
- Commits b07b49735, c52884d90, 416e73510, b68bad56d are ancestors of HEAD.
