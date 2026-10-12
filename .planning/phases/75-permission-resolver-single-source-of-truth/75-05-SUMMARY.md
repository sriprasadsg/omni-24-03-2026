---
phase: 75-permission-resolver-single-source-of-truth
plan: 05
subsystem: auth
tags: [rbac, ldap, saml, privilege-escalation, ast-drift-test, archive, pytest]
status: complete

requires:
  - phase: 75-01
    provides: rbac_defaults.builtin_role_keys / SUPER_ADMIN_KEY, RBACService._normalize_role
  - phase: 75-04
    provides: role_assignment.assert_can_assign_role (D-20 ceiling)
provides:
  - LDAP group-mapping and SAML attribute-mapping writes gated by the role-assignment ceiling
  - LDAPUserSyncer.sync_user / SAMLUserProvisioner.provision_user refuse any super-admin-tier role from a directory
  - archive/backend-rbac-oneoffs/ (five role-writing scripts moved with git mv, plus ARCHIVED.md)
  - AST drift guard (test_no_second_permission_table) with scanner self-tests
affects: [76 manifest, any future module that adds a role-to-permission literal]

plan_head_before: a7c071338afc8afed7ac5b928ac45fde46756f76
plan_head_after: 239b3beb2cd57a1967b6dc4a24cefd3a2a47fcf6

actuals:
  tokens: 21000
  tasks: 3
  commits: 5

tech-stack:
  added: []
  patterns:
    - "Directory-sourced roles are checked twice: at write time (ceiling) and at apply time (super-admin tier hard block), so old mappings need no migration"
    - "Drift guard scans top-level backend/*.py by AST with a per-(file, variable) allowlist carrying a reason"

key-files:
  created:
    - archive/backend-rbac-oneoffs/ARCHIVED.md
  modified:
    - backend/ldap_endpoints.py
    - backend/ldap_service.py
    - backend/sso_endpoints.py
    - backend/saml_mapping.py
    - backend/tests/test_ldap_service.py
    - backend/tests/test_sso_saml.py
    - backend/tests/test_rbac_defaults.py
  moved:
    - archive/backend-rbac-oneoffs/{fix_rbac_integrations,update_sbom_roles,update_all_sbom_roles,enable_compliance_for_admin,reset_db_fresh}.py

key-decisions:
  - "Mapping routes pass target_tenant_id = scope tenant or the caller's tenant (super-admins writing platform config fall back to their own tenant; they pass rule 3 anyway)"
  - "Apply-time block sets role = None so the existing existing-user/default-role handling does the rest, with no session revocation and no schema change"
  - "Scanner (b) requires a non-empty list whose strings all match the permission pattern or equal *, so an empty permissions list on a user-like document is not flagged"

patterns-established:
  - "Test fakes for ceiling-gated routes need a roles collection on the raw handle (db._db.roles) and itam_admin in the manage:assets role set"

requirements-completed: [ACC-01, ACC-02]

coverage:
  - id: D1
    description: "LDAP group-mapping write: tenant admin cannot map to super_admin (403, nothing stored); itam_admin cannot map to admin or Tenant Admin; itam_admin can map to itam_user; admin to itam_admin and unknown-role 400 unchanged"
    requirement: "ACC-01"
    verification:
      - kind: integration
        ref: "backend/tests/test_ldap_service.py#TestLDAPGroupMappingEndpoint"
        status: pass
    human_judgment: false
  - id: D2
    description: "SAML attribute-mapping write follows the same ceiling (super_admin and admin refused for the wrong callers, itam_user allowed)"
    requirement: "ACC-01"
    verification:
      - kind: integration
        ref: "backend/tests/test_sso_saml.py#TestSAMLAttributeMappingEndpoint"
        status: pass
    human_judgment: false
  - id: D3
    description: "Apply time: sync_user and provision_user keep the existing role (or itam_viewer for a new user), log a warning and do not revoke sessions when a mapping resolves to super_admin, Super Admin or platform-admin"
    requirement: "ACC-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_ldap_service.py#test_sync_user_refuses_super_admin_role_for_existing_user"
        status: pass
      - kind: unit
        ref: "backend/tests/test_sso_saml.py#test_provision_user_refuses_super_admin_role_for_existing_user"
        status: pass
    human_judgment: false
  - id: D4
    description: "Five role-writing one-off scripts archived with git mv (history kept) and ARCHIVED.md; four related scripts still in backend/"
    requirement: "ACC-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_rbac_defaults.py#test_role_writing_scripts_are_archived"
        status: pass
    human_judgment: false
  - id: D5
    description: "AST drift guard fails on a second role-keyed permission dict, role document literal or permission-string list in backend/*.py; scanners proven to fire on synthetic input"
    requirement: "ACC-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_rbac_defaults.py#test_no_second_permission_table"
        status: pass
      - kind: unit
        ref: "backend/tests/test_rbac_defaults.py#test_scanner_flags_role_keyed_dict"
        status: pass
    human_judgment: false

duration: 65 min
completed: 2026-10-12
---

# Phase 75 Plan 05: Directory Mapping Ceiling, Script Archive and Drift Guard Summary

**LDAP and SAML group mappings now obey the role-assignment ceiling when written and can never apply the super-admin tier at sign-in; the five role-writing one-off scripts are archived with history; an AST test fails the build if a second role-to-permission table appears in backend/*.py.**

## Performance

- **Duration:** ~65 min
- **Completed:** 2026-10-12T22:57Z
- **Tasks:** 3
- **Files modified:** 7 edited, 5 moved, 1 created

## Accomplishments
- `POST /api/admin/ldap/group-mapping` and `POST /api/admin/sso/saml/attribute-mapping` call `assert_can_assign_role` before saving: a tenant admin or itam_admin can no longer map a directory group to `super_admin`, and itam_admin cannot map to `admin` or `Tenant Admin`.
- `LDAPUserSyncer.sync_user` and `SAMLUserProvisioner.provision_user` drop a role that normalizes to the super-admin tier (covers `Super Admin`, `platform-admin`), log a warning, and keep the existing or default role. No data migration; existing mappings stay readable.
- Both mapping validators read `rbac_defaults.builtin_role_keys()` instead of the derived RBACService dict.
- Moved `fix_rbac_integrations.py`, `update_sbom_roles.py`, `update_all_sbom_roles.py`, `enable_compliance_for_admin.py`, `reset_db_fresh.py` with `git mv` to `archive/backend-rbac-oneoffs/`; `git log --follow` on `reset_db_fresh.py` shows 6 commits.
- Drift guard: two pure AST scanners (permission-string lists, role-keyed dicts and role document literals) over every top-level `backend/*.py` (BOM-safe), with a per-(file, variable) tier-list allowlist. With the allowlist emptied the scanners report exactly the five known tier lists (six literal sites), so the guard demonstrably fires.

## Task Commits

1. **Task 1 (TDD): LDAP mappings** - `23c91c926` (test, RED: 5 failing on assertions), `5692912d5` (feat, GREEN)
2. **Task 2 (TDD): SAML mappings** - `432763597` (test, RED: 4 failing on assertions), `ad22f7da1` (feat, GREEN)
3. **Task 3: archive and drift guard** - `239b3beb2` (chore)

**Plan metadata:** committed separately (docs: complete plan)

## TDD Gate Compliance

RED and GREEN commits present for Tasks 1 and 2. RED evidence: the endpoint tests failed with `assert 200 == 403`; the sync/provision tests failed with `assert 'super_admin' == 'itam_user'` / `'itam_viewer'` (target assertions on the planned behavior, not collection or import faults). The green `test_itam_admin_can_map_*_to_itam_user` tests passed before implementation by design (they pin legitimate behavior). No refactor commits.

## Files Created/Modified
- `backend/ldap_endpoints.py`, `backend/sso_endpoints.py` - ceiling check before `upsert_mapping`
- `backend/ldap_service.py`, `backend/saml_mapping.py` - apply-time super-admin refusal; validators from `builtin_role_keys()`
- `backend/tests/test_ldap_service.py`, `backend/tests/test_sso_saml.py` - `roles` collection on fakes, `itam_admin` in `_ADMIN_ROLES`, 6 + 5 new tests
- `backend/tests/test_rbac_defaults.py` - drift guard, scanner self-tests, archive test (163 lines appended)
- `archive/backend-rbac-oneoffs/` - five moved scripts and `ARCHIVED.md`

## Decisions Made
See `key-decisions` in the frontmatter.

## Deviations from Plan

**1. [Rule 1 - Bug in own test] Mock aliasing in the existing-user refusal test**
- **Found during:** Task 1 GREEN
- **Issue:** `sync_user` mutates the `doc` dict it passed to `update_one` as `$set`, so asserting on `await_args` saw the mutated role, failing a correct implementation.
- **Fix:** the test captures a copy of `$set` inside an `update_one` side effect (same in the SAML test).
- **Files modified:** backend/tests/test_ldap_service.py, backend/tests/test_sso_saml.py
- **Committed in:** `5692912d5` / `432763597`-era test files (LDAP fix in `5692912d5`, SAML test written correctly the first time)

**Total deviations:** 1 auto-fixed (test-authoring). **Impact:** none on production code.

## Issues Encountered
None blocking. Full backend suite: 3223 passed, 47 skipped, 0 failed (baseline in plan: 2878 passed; the rest are tests added by Plans 01-05). `test_route_auth_baseline.py` passes.

Pre-existing working-tree changes included: none. The orchestrator committed the earlier fixture edits to `test_ldap_service.py`/`test_sso_saml.py` as `a7c071338` before this plan started; `ldap_service.py` had no uncommitted changes at start. Other archive folders were left untracked.

## Known Stubs
None.

## Threat Flags
None. No new endpoints or trust boundaries; T-75-20..23 mitigated as planned. `bandit_app.json` still names the moved scripts (generated report, left as instructed).

## User Setup Required
None - no external service configuration required. No services were restarted or deployed; live database untouched. Running backend picks up these changes only after the user restarts it.

## Next Phase Readiness
Last plan of Phase 75; ready for phase verification.

## Self-Check: PASSED

---
*Phase: 75-permission-resolver-single-source-of-truth*
*Completed: 2026-10-12*
