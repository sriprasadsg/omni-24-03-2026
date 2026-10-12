---
phase: 75-permission-resolver-single-source-of-truth
plan: 04
subsystem: auth
tags: [rbac, privilege-escalation, role-assignment, bundles, fastapi, pytest]
status: complete

requires:
  - phase: 75-01
    provides: rbac_defaults.ceiling_allows / builtin_role_keys / SUPER_ADMIN_KEY, rbac_service.effective_permissions, tests.rbac_test_support
provides:
  - backend/role_assignment.py assert_can_assign_role, the one shared D-20 ceiling helper (Plan 05 reuses it for LDAP/SAML mapping writes)
  - bundle assignment routes (PUT/PATCH/DELETE /api/bundles/tenant/{id}/assign) gated by require_super_admin
  - user create/update gated by the ceiling; role names validated against rbac_defaults.builtin_role_keys()
affects: [75-05 LDAP/SAML mapping ceiling and drift test, 76 manifest]

plan_head_before: 639462a6130d72e6ed5c3bb15f8ea44c5feffafe
plan_head_after: 1876d002868e34ade68d20ad5022e62aecca0f95

actuals:
  tokens: 14000
  tasks: 2
  commits: 4

tech-stack:
  added: []
  patterns:
    - "Both sides of the assignment ceiling come from the same async resolver (effective_permissions), so tenant-scoped role documents count"
    - "Super-admin tier decided by role-name normalization only, never by * in a document"
    - "Resolver errors fail closed as 503 instead of allowing the assignment"

key-files:
  created:
    - backend/role_assignment.py
    - backend/tests/test_role_assignment_ceiling.py
  modified:
    - backend/bundle_endpoints.py
    - backend/user_endpoints.py
    - backend/tests/test_bundles_and_reports.py
    - backend/tests/test_user_crud.py
    - backend/tests/test_session_revocation.py

key-decisions:
  - "Bundle assignment uses Depends(require_super_admin) on all three write routes; the read routes are untouched (read-side observation stays with Phase 76)"
  - "Ceiling helper lives in role_assignment.py, not rbac_service.py, so this plan does not share a file with Plans 02/03"
  - "Self-change rule (rule 2) runs before the super-admin shortcut (rule 3), so a super-admin cannot change its own role either"
  - "create_user validates the role name (400) first, resolves the target tenant, then runs the ceiling (403/503) before the tenant-existence check"

patterns-established:
  - "Escalation regressions are written against the endpoint with a role-aware fake of verify_permission plus a FakeDB exposing roles and _db"

requirements-completed: [ACC-01, ACC-02]

coverage:
  - id: D1
    description: "Tenant Admin gets 403 on PUT/PATCH/DELETE bundle assignment for its own and another tenant, including with a tenant role document granting manage:tenants; Super Admin still gets 200; no tenants write on refusal"
    requirement: "ACC-02"
    verification:
      - kind: integration
        ref: "backend/tests/test_bundles_and_reports.py#TestBundleAssignSuperAdminOnly"
        status: pass
    human_judgment: false
  - id: D2
    description: "assert_can_assign_role allows exactly the D-20/D-21 caller x target matrix (100 parametrized cases), refuses the super-admin tier to non-super callers by name, refuses self role change, counts tenant-scoped documents, ignores * documents for the super-admin tier, and fails closed on a role-store error"
    requirement: "ACC-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_role_assignment_ceiling.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "itam_admin gets 403 creating admin/Tenant Admin users and promoting or changing its own role, still creates itam_user/itam_viewer users; Tenant Admin creates itam_admin; unknown roles are 400 before the ceiling; role-store error is 503"
    requirement: "ACC-01"
    verification:
      - kind: integration
        ref: "backend/tests/test_user_crud.py#TestRoleAssignmentCeiling"
        status: pass
    human_judgment: false

duration: 40 min
completed: 2026-10-12
---

# Phase 75 Plan 04: Bundle Super-Admin Guard and Role-Assignment Ceiling Summary

**Bundle assignment is now platform-super-admin only, and user create/update obey a shared effective-permission ceiling (`assert_can_assign_role`) so an `itam_admin` can no longer mint or become an `admin`/`Tenant Admin`.**

## Performance

- **Duration:** about 40 min
- **Tasks:** 2 of 2 (both TDD)
- **Files:** 2 created, 5 modified

## Accomplishments

- `bundle_endpoints.py`: PUT, PATCH and DELETE `/tenant/{tenant_id}/assign` use `Depends(require_super_admin)`; docstrings say why (the `tenants` collection is isolation-exempt, so the write is cross-tenant by construction, D-06). `manage:tenants` no longer appears in the module.
- `backend/role_assignment.py`: `assert_can_assign_role(db, caller, target_role, *, target_tenant_id, target_email=None, current_role=None)` applies D-20 in order: super-admin tier by normalized name; no self role change (same role re-sent is fine); super-admin caller allowed; otherwise `ceiling_allows(effective_permissions(caller), effective_permissions(target))`. Any resolver exception is logged and becomes 503 "Role store unavailable; role assignment refused".
- `user_endpoints.py`: `_VALID_ROLE_KEYS = rbac_defaults.builtin_role_keys()`; the `_ELEVATED_ROLE_KEYS` constant and both checks are gone; `create_user` and `update_user` call the helper (400 for unknown names first, then 403/503). Cross-tenant check, session revocation on role change and every other field are unchanged.
- Tests: 12 new bundle tests, 178 helper tests (100-case matrix plus super-tier, self-change, tenant-document, `*`-document and store-error cases), 10 endpoint regressions in `TestRoleAssignmentCeiling`.

## Task Commits

1. **Task 1 RED:** failing super-admin-only bundle tests - `8d7c6c4e0` (test)
2. **Task 1 GREEN:** bundle routes require a platform super-admin - `18feddde8` (feat)
3. **Task 2 RED:** failing ceiling tests - `f3e415cdc` (test)
4. **Task 2 GREEN:** shared ceiling helper wired into user create/update - `1876d0028` (feat)

## TDD Evidence

- **Task 1 RED:** 3 of 12 target tests failed on the planned assertion (`200 == 403`) for the tenant-document case across PUT/PATCH/DELETE; the plain Tenant Admin cases already returned 403 after Plan 01 removed `manage:tenants` from the defaults, so the document case is the one that proves the second safeguard. Semantic assessment: target tests executed and failed for the intended reason (a role document granting `manage:tenants` unlocked the route).
- **Task 2 RED:** 5 of 36 `test_user_crud.py` tests failed on planned assertions (`201 == 403` for itam_admin creating admin and Tenant Admin, `200 == 403` for self-promotion and self role change, `201 == 503` for the store-outage case). The new `test_role_assignment_ceiling.py` could not be collected at RED (`ModuleNotFoundError: role_assignment`), which is a load failure and not RED evidence by itself; the endpoint regressions above are the semantic RED evidence for that task. Both files were committed together in the RED commit.
- **GREEN/REFACTOR:** no refactor commit was needed.

## Verification

- Plan verification set: `test_bundles_and_reports.py` 40 passed (`-k SuperAdminOnly` 12), `test_role_assignment_ceiling.py` 178 passed, `test_user_crud.py` 36 passed (`-k RoleAssignmentCeiling` 10), `test_session_revocation.py` + `test_rbac.py` 62 passed.
- Full backend suite: 3206 passed, 47 skipped, 0 failed (75-01 baseline 2951 passed).
- Acceptance greps: `Depends(require_super_admin)` 3, `manage:tenants` 0 in `bundle_endpoints.py`; `assert_can_assign_role(` 2, `_ELEVATED_ROLE_KEYS` 0, `builtin_role_keys()` 1 in `user_endpoints.py`; 4 matching imports in `role_assignment.py`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] test_session_revocation.py fixture had no roles lookup**
- **Found during:** Task 2 (running the third verify command)
- **Issue:** `_users_client` builds `db` as a bare `MagicMock`; the resolver reads `db._db.roles.find_one` which is not awaitable, so the ceiling refused with 503 and two existing user-update tests failed.
- **Fix:** added `db._db.roles.find_one = AsyncMock(return_value=None)` to the fixture. The file is not in the plan's `files_modified`, but the plan's acceptance criteria require this file to keep passing.
- **Files modified:** backend/tests/test_session_revocation.py
- **Commit:** 1876d0028

**Total deviations:** 1 auto-fixed (blocking test fixture). **Impact:** none on production behaviour.

## Pre-existing working-tree changes included

None. Contrary to the plan's note, `backend/user_endpoints.py` had no uncommitted changes at execution time, and none of the other touched files carried unrelated hunks. Only the plan's files were staged.

## Issues Encountered

- `backend/rate_limiter.py` uses Redis storage when available, so running `test_session_revocation.py` several times within a minute produced `429` in its login tests (counters persist across pytest processes). This is a pre-existing test-environment trait and not a regression: after waiting a minute the file passes, and the full suite run passed. Repeated login-test runs against the shared limiter are best avoided.

## Known Stubs

None.

## Threat Flags

None beyond the plan's threat register. T-75-15 (bundle writes), T-75-16 (role escalation), T-75-17 (self change), T-75-18 (`*` document) and T-75-19 (store outage) are each covered by a named test above.

## Next Plan Readiness

Ready for 75-05: `role_assignment.assert_can_assign_role` can be reused as-is for LDAP/SAML mapping writes (pass `target_tenant_id`, leave `target_email`/`current_role` unset). Live system untouched: no service restarts, deploys, or writes to `omni_platform`; no live endpoint was exercised.

## Self-Check: PASSED

- Files: backend/role_assignment.py, backend/tests/test_role_assignment_ceiling.py, backend/bundle_endpoints.py, backend/user_endpoints.py present.
- Commits 8d7c6c4e0, 18feddde8, f3e415cdc, 1876d0028 are ancestors of HEAD.
