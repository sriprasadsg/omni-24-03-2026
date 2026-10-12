---
phase: 75-permission-resolver-single-source-of-truth
fixed_at: 2026-10-12T23:15:00Z
review_path: .planning/phases/75-permission-resolver-single-source-of-truth/75-REVIEW.md
iteration: 1
findings_in_scope: 9
fixed: 9
skipped: 0
status: all_fixed
---

# Phase 75: Code Review Fix Report

**Fixed at:** 2026-10-12
**Source review:** .planning/phases/75-permission-resolver-single-source-of-truth/75-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 9 (1 Critical, 8 Warning; Info excluded by `fix_scope: critical_warning`)
- Fixed: 9 (WR-04 and WR-06 fixed in part, see their notes)
- Skipped: 0

**Verification:** run in the main checkout (`workflow.use_worktrees` is `false`, so no worktree was created). Full backend suite `backend/venv/bin/python -m pytest backend/tests -q -p no:cacheprovider`: 3276 passed, 47 skipped. `npx vitest run src/__tests__`: 27 files, 209 tests passed. `tsc --noEmit` reported no errors in the touched frontend files. No live service, deploy or `omni_platform` write was involved.

Findings marked "requires human verification" are logic changes: tests and syntax checks pass, but the intended policy should be confirmed by a person.

## Fixed Issues

### CR-01: Ceiling is not applied to the target account, so a lower admin can take over a higher-privileged user

**Status:** fixed: requires human verification
**Files modified:** `backend/role_assignment.py`, `backend/user_endpoints.py`, `backend/tests/test_user_crud.py`
**Commit:** 1a6592470
**Applied fix:** Added `assert_can_manage_account` to `role_assignment.py`, the account-side twin of `assert_can_assign_role`. It reuses the same resolver and `rbac_defaults.ceiling_allows` closure rather than a second rule. A super-admin caller may manage any account. A super-admin-tier account is managed only by a super-admin. Otherwise the target's current role must fit inside the caller's effective permissions. A role-store error refuses the call (503). It runs in `update_user` (password, status, role, tenant and profile changes) and in `delete_user`, after the existing tenant check and before any mutation. Equal-role accounts stay manageable. New `TestTargetAccountCeiling` tests cover itam_admin against Tenant Admin, admin, tenant_admin, analyst and Super Admin for password, status, rename and delete (403 each, nothing written); the happy paths; a Tenant Admin against a Super Admin account in the same tenant; the super-admin bypass; and the 503 fail-closed case.

### WR-01: Resolver honours `*` and super-admin-only permissions from non-super role documents

**Status:** fixed: requires human verification
**Files modified:** `backend/rbac_service.py`, `backend/tests/test_rbac.py`, `backend/tests/test_role_assignment_ceiling.py`, `backend/tests/test_effective_permissions.py`
**Commit:** 709d8e77a
**Applied fix:** `effective_permissions` drops `*` and every `SUPER_ADMIN_ONLY_PERMISSIONS` entry found in role documents. Two existing tests asserted the old behaviour and were updated: `test_wildcard_permission_grants_everything` (now expects 403) and `test_a_star_document_cannot_unlock_the_super_admin_tier` (a `*` document no longer lets an itam_admin assign `admin`). New tests check the resolver output and that a viewer with a `*` document is denied `manage:tenants` and `manage:users`.

### WR-02: `GET /api/bundles/tenant/{tenant_id}/features` lets any authenticated user read any tenant's entitlements

**Status:** fixed
**Files modified:** `backend/bundle_endpoints.py`, `backend/tests/test_bundles_and_reports.py`
**Commit:** 4cb11feef
**Applied fix:** The route returns 403 unless the caller is a super-admin or `tenant_id` equals their own tenant. The check runs before the database lookup, so a missing tenant also answers 403 for a foreign caller and ids cannot be enumerated. The existing 404 test now uses a super-admin. New tests cover a foreign tenant and a nonexistent tenant (403, no lookup made) and the super-admin read.

### WR-03: PATCH bundle assignment skips the validation PUT performs

**Status:** fixed
**Files modified:** `backend/bundle_endpoints.py`, `backend/tests/test_bundles_and_reports.py`
**Commit:** eb0e8d90f
**Applied fix:** One `_reject_unknown_features` helper validates `custom_features` and `blocked_features` in both PUT and PATCH. Parametrized tests check that both routes return 400 and write nothing.

### WR-04: Role-mapping ceiling is write-time only

**Status:** fixed in part: requires human verification
**Files modified:** `backend/ldap_service.py`, `backend/saml_mapping.py`, `backend/ldap_endpoints.py`, `backend/sso_endpoints.py`, `backend/tests/test_ldap_service.py`, `backend/tests/test_sso_saml.py`
**Commit:** c0826c732
**Applied fix:**
- `delete_group_mapping` and `delete_attribute_mapping` now load the mapping (new `get_mapping` on both mappers) and apply `assert_can_assign_role` to its role before deleting. A mapping above the caller's role gives 403; a missing mapping still gives 404.
- `sync_user` and `provision_user` no longer replace the role of an existing account that is in the super-admin tier. A warning is logged, the role is kept and no session revocation happens.
- Tests cover both deletes (above and within the caller's role) and both syncers.

**Not done (design change, left for a later phase):** storing the writer's identity or role on each mapping and re-validating it at every login or sync. This needs a mapping-document schema change and a migration for existing mappings, which is outside a review fix. Mappings written before the ceiling existed can still grant a tenant-level role at apply time; only the super-admin tier is re-checked there.

### WR-05: Session revocation after a role change runs after the write and can fail open

**Status:** fixed: requires human verification
**Files modified:** `backend/user_endpoints.py`, `backend/ldap_service.py`, `backend/saml_mapping.py`, `backend/tests/test_user_crud.py`, `backend/tests/test_ldap_service.py`, `backend/tests/test_sso_saml.py`
**Commit:** e8eb74a90
**Applied fix:** Revocation now runs before the write in `update_user`, in `delete_user` and in the LDAP and SAML role-change paths. If the cutoff cannot be stored, the request or login fails and nothing was persisted, so a demotion can no longer persist while the old session survives. Tests check that a failing revocation leaves the role unchanged, the account undeleted and the directory update unwritten, and that revocation happens while the old role is still stored. A login that races between the revoke and the write can still mint an old-role token for that instant; a second post-write revoke was tried and dropped because it broke the existing exactly-once revocation tests.

### WR-06: Role documents are matched by exact spelling

**Status:** fixed in part: requires human verification
**Files modified:** `backend/rbac_service.py`, `backend/tests/test_effective_permissions.py`
**Commit:** 813ff3129
**Applied fix:** New `_role_document_names` makes the resolver look up documents under the raw string, the normalized key, and the seeded `name` and `display_name` of every built-in that shares the role's canonical key. A tenant override filed under "Tenant Admin" now applies to users stored as `tenant_admin`, `admin` or `Admin`, and `assert_can_assign_role` sees the same set. Parametrized tests cover the spellings.

**Not done:** the second half of the finding (whether `isEditable` should have any effect on the shared documents, since the boot-time `$set` overwrites them and tenant documents can only add permissions) is a product decision, not a code defect. The union-only merge is now stated in the `effective_permissions` docstring; whether to change it needs a decision.

### WR-07: Frontend super-admin detection disagrees with the backend and ignores `*`

**Status:** fixed
**Files modified:** `utils/permissions.ts`, `App.tsx`, `src/__tests__/permissions.test.ts`
**Commit:** d10da51c1
**Applied fix:** `isSuperAdminRoleName` mirrors the backend normalizer (lower-case, trim, spaces and hyphens to underscores, `superadmin` and `platform_admin` folded into `super_admin`). `derivePermissionState` treats a delivered `*` as a super grant and skips the tenant intersection. `handleSetCurrentView` in `App.tsx` calls the helper instead of its own two-name check. Tests added for `super-admin`, `platform_admin`, `platform admin`, and a custom-named role delivered `["*"]`.

### WR-08: D-26 cache hygiene covers only `omni_cache_roles`

**Status:** fixed
**Files modified:** `services/apiService.ts`, `src/__tests__/permissions.test.ts`
**Commit:** 1e874d982
**Applied fix:** `clearSessionCaches()` removes every `omni_cache_*` sessionStorage key and resets the module-level `USERS`, `ROLES`, `TENANTS` and `ASSETS`. It runs on logout and session expiry. The 403 branch of `fetchWithCache` now also calls `updateLocalVar` with the empty value. Tests check that all cache keys are removed while unrelated keys stay, and that the previous users list is not served offline after logout.

## Skipped Issues

None. Info findings (IN-01 to IN-05) were out of scope for `fix_scope: critical_warning` and were not touched.

---

_Fixed: 2026-10-12_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
