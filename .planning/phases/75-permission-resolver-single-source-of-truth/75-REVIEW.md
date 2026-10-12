---
phase: 75-permission-resolver-single-source-of-truth
reviewed: 2026-10-12T00:00:00Z
depth: standard
files_reviewed: 38
files_reviewed_list:
  - App.tsx
  - archive/backend-rbac-oneoffs/ARCHIVED.md
  - archive/backend-rbac-oneoffs/enable_compliance_for_admin.py
  - archive/backend-rbac-oneoffs/fix_rbac_integrations.py
  - archive/backend-rbac-oneoffs/reset_db_fresh.py
  - archive/backend-rbac-oneoffs/update_all_sbom_roles.py
  - archive/backend-rbac-oneoffs/update_sbom_roles.py
  - backend/app_startup.py
  - backend/authentication_endpoints.py
  - backend/bundle_endpoints.py
  - backend/ldap_endpoints.py
  - backend/ldap_service.py
  - backend/mfa_endpoints.py
  - backend/rbac_defaults.py
  - backend/rbac_service.py
  - backend/rbac_utils.py
  - backend/role_assignment.py
  - backend/role_endpoints.py
  - backend/saml_mapping.py
  - backend/sso_endpoints.py
  - backend/tests/rbac_test_support.py
  - backend/tests/test_bundles_and_reports.py
  - backend/tests/test_effective_permissions.py
  - backend/tests/test_ldap_service.py
  - backend/tests/test_login_me_permissions.py
  - backend/tests/test_rbac.py
  - backend/tests/test_rbac_defaults.py
  - backend/tests/test_role_assignment_ceiling.py
  - backend/tests/test_role_seeding.py
  - backend/tests/test_roles_endpoint.py
  - backend/tests/test_seed_database_step_isolation.py
  - backend/tests/test_session_revocation.py
  - backend/tests/test_sso_saml.py
  - backend/tests/test_user_crud.py
  - backend/user_endpoints.py
  - services/apiService.ts
  - src/__tests__/permissions.test.ts
  - utils/permissions.ts
findings:
  critical: 1
  warning: 8
  info: 5
  total: 14
status: issues_found
---

# Phase 75: Code Review Report

**Reviewed:** 2026-10-12
**Depth:** standard
**Files Reviewed:** 38 (test files were read for coverage gaps only)
**Status:** issues_found

## Summary

The resolver and the role table are well structured. The single table in `rbac_defaults.py` has no import cycles. `effective_permissions` fails closed in `verify_permission` and `assert_can_assign_role`. Every raw `db._db.roles` read carries an explicit `tenantId` (`_role_docs`, `find_role_doc`, `list_roles`). The five archived scripts are referenced only by `ARCHIVED.md` and `test_rbac_defaults.py`. Nothing imports or invokes them.

The role-assignment ceiling has one real hole. It is applied to the role being granted, but never to the account being modified. That leaves a privilege-escalation path in user CRUD (CR-01). Secondary issues:

- The resolver trusts `*` and super-admin-only permissions found in tenant role documents.
- The mapping ceilings are write-time only.
- A bundle read endpoint leaks other tenants' entitlements.
- The frontend cache and super-admin handling lag the backend.

No structural (fallow) findings were supplied for this review.

## Critical Issues

### CR-01: Ceiling is not applied to the target account, so a lower admin can take over a higher-privileged user

**File:** `backend/user_endpoints.py:318-411` (update) and `:413-447` (delete). Gate: `backend/itam_asset_endpoints.py:96-116`.

**Issue:** `assert_can_assign_role` runs only when `updates.role is not None`. It compares the role being granted with the caller's permissions. Nothing compares the target user's existing role with the caller's permissions. The gate for these endpoints, `_require_itam_admin_session_only`, only demands `manage:assets`.

The built-in `itam_admin` role holds `manage:assets`. So an `itam_admin` (or any role with `manage:assets`) in tenant A can do the following to a `tenant_admin` user in the same tenant, with no role field in the body:

- `PUT /api/users/{id}` with `{"password": "..."}`. This passes `validate_password_complexity`, writes `password`, and revokes sessions. The caller can then log in as the tenant admin, which is a full escalation.
- `PUT {"status": "inactive"}` to disable the tenant admin.
- `DELETE /api/users/{id}` to delete the tenant admin.

The same applies to any user whose role is above the caller's. This includes a super-admin account that lives in the same tenant (the tenant check `target_user.tenantId != get_tenant_id()` only blocks other tenants). It defeats the point of the D-18/D-20 ceiling, because role assignment is blocked but credential takeover is not. The tests (`test_user_crud.py:640-730`, `test_role_assignment_ceiling.py`) only exercise the `role` field. There is no password, status or delete test against a higher-privileged target.

**Fix:** In `update_user` and `delete_user`, after loading `target_user` and before any mutation, require that the caller outranks or equals the target's current role:

```python
async def _assert_can_manage_target(db, current_user, target_user):
    if is_super_admin(current_user.role):
        return
    target_role = target_user.get("role")
    if target_role:
        # Re-uses the same ceiling: caller must hold everything the target's role grants,
        # and only a super-admin may touch a super-admin-tier account.
        await assert_can_assign_role(
            db, current_user, target_role,
            target_tenant_id=target_user.get("tenantId"),
            target_email=target_user.get("email"),
            current_role=target_role,   # self edits stay allowed (same role)
        )
```

Call it in both handlers. Add tests for itam_admin -> tenant_admin password reset, status change and delete, each expecting 403.

## Warnings

### WR-01: Resolver honours `*` and super-admin-only permissions from non-super role documents

**File:** `backend/rbac_service.py:58-76`, `backend/rbac_utils.py:75-86`, `backend/rbac_defaults.py:110-118`.

**Issue:** `effective_permissions` appends every permission string from the matching `roles` documents, including `*` and the `SUPER_ADMIN_ONLY_PERMISSIONS` set (`manage:tenants` and others). `verify_permission` and `has_permission` then treat `*` as a full grant. A document such as `{name: "viewer", tenantId: <tenant>, permissions: ["*"]}` turns every viewer in that tenant into a de facto super-admin for every `require_permission` and `has_permission` gate. That includes cross-tenant `manage:tenants` gates.

`SUPER_ADMIN_ONLY_PERMISSIONS` is defined, tested for table purity, and never enforced at resolve time. `test_a_star_document_cannot_unlock_the_super_admin_tier` documents the gap: it asserts that a `*` document lets an `itam_admin` assign `admin`. It only protects the literal super-admin role name. No API writes tenant role documents today, so exploitation needs DB access or a future role editor. The invariant should still live in the resolver, not in whoever writes documents.

**Fix:** In `effective_permissions`, drop `*` and `SUPER_ADMIN_ONLY_PERMISSIONS` from any document-derived permissions when the key is not `super_admin`:

```python
banned = rbac_defaults.SUPER_ADMIN_ONLY_PERMISSIONS | {"*"}
perms.extend(p for p in (doc.get("permissions") or []) if p and p not in banned)
```

Update the test above to expect a 403.

### WR-02: `GET /api/bundles/tenant/{tenant_id}/features` lets any authenticated user read any tenant's entitlements

**File:** `backend/bundle_endpoints.py:83-117`.

**Issue:** The endpoint depends only on `get_current_user`. The `tenants` collection is exempt from tenant isolation (the module's own docstring says so for the write routes). Any user of any tenant can pass an arbitrary `tenant_id` and get:

- that tenant's assigned bundles,
- its custom and blocked features,
- the resolved feature list.

A 404 versus 200 response also lets them enumerate valid tenant ids. Phase 75 made the writes super-admin-only (D-06) but left this cross-tenant read open.

**Fix:** Allow the call only when `is_super_admin(current_user.role)` or `tenant_id == current_user.tenant_id`; otherwise return 403 (or 404 to avoid enumeration):

```python
if not (is_super_admin(current_user.role) or tenant_id == current_user.tenant_id):
    raise HTTPException(status_code=403, detail="Not authorized for this tenant")
```

### WR-03: PATCH bundle assignment skips the validation PUT performs

**File:** `backend/bundle_endpoints.py:189-198`.

**Issue:** `PUT /assign` rejects unknown `custom_features` (`:143-145`). `PATCH /assign` validates only `assigned_bundles`. `custom_features` is written unchecked, so arbitrary feature strings can be persisted and then fed to `resolve_tenant_features`. `blocked_features` is never validated in either route. This is super-admin-only, so impact is data integrity, but the two routes now disagree.

**Fix:** Share one validator for `custom_features` (and `blocked_features`) between PUT and PATCH.

### WR-04: Role-mapping ceiling is write-time only; apply time checks nothing but the super-admin tier

**File:** `backend/ldap_service.py:434-444`, `backend/saml_mapping.py:59-69`, `backend/ldap_endpoints.py:189-197`, `backend/sso_endpoints.py:389-397`.

**Issue:**
- Mappings written before this phase, or by a writer who was later demoted, still grant `tenant_admin` to directory users at every login or sync. Only the super-admin tier is re-checked at apply time.
- `delete_group_mapping` and `delete_attribute_mapping` have no ceiling at all. Any `manage:assets` holder can delete a mapping that grants a role above their own.
- `sync_user` and `provision_user` overwrite the role of an existing account in the target tenant, with no check on that account's current role. A mapping can therefore demote or replace a higher-privileged local account that shares an email with a directory entry.

**Fix:** At apply time, store the writer's identity or role on the mapping and re-validate. At minimum, refuse to downgrade or overwrite an existing account whose role is the super-admin tier, and apply the ceiling to deletes (`assert_can_assign_role` against the mapping's role).

### WR-05: Session revocation after a role change runs after the write and can fail open

**File:** `backend/user_endpoints.py:394-406`, `backend/ldap_service.py:466-468`, `backend/saml_mapping.py:91-93`.

**Issue:** `revoke_user_sessions` raises if the cutoff cannot be stored (`authentication_service.py:110-135`). In `update_user` the role or password change is already persisted before revocation runs. If the revocation write fails, the caller gets a 500 and the audit log entry is skipped. The user's old, possibly higher-privilege, session stays valid because the JWT carries the old role. A demotion thereby fails open. The same ordering exists in the LDAP and SAML paths.

**Fix:** Revoke before or atomically with the write, or catch the failure, log it at error level, and still write the audit record. Alternatively, roll back the field change when revocation fails.

### WR-06: Role documents are matched by exact spelling, so tenant overrides and the ceiling are spelling-dependent

**File:** `backend/rbac_service.py:38-55, 72-75`.

**Issue:** `effective_permissions` looks up documents only by the raw role string and its normalized key. Seeded documents use display names (`"Tenant Admin"`, `"admin"`, `"analyst"`). A user stored as `tenant_admin` never matches the `"Tenant Admin"` document or a tenant-scoped override of it. A user stored as `Tenant Admin` matches it. The same logical role resolves differently depending on how it was typed, and `assert_can_assign_role` then evaluates the target differently too.

Separately, seeding and resolution disagree on mutability. `analyst`, `user` and `viewer` are seeded `isEditable: True`, yet the boot-time `$set` overwrites the shared documents every start. The union-only merge means a tenant document can only add permissions, never remove them.

**Fix:** Look up documents by a normalized-name field (store `name_key` at seed time), or try every alias of the role. Decide and document whether `isEditable` has any effect on the shared documents.

### WR-07: Frontend super-admin detection disagrees with the backend and ignores `*`

**File:** `utils/permissions.ts:3-23`, `App.tsx:1329-1335`.

**Issue:**
- The backend normalizer maps `super-admin`, `Super Admin`, `platform_admin`, `platform admin` and `superadmin` to `super_admin`. The `create_user` path accepts any of these, because only the normalized key is validated. `SUPER_ADMIN_ROLE_NAMES` has `'platform-admin'` but not `'platform_admin'`, `'platform admin'` or `'super-admin'`.
- For such a user the server delivers `["*"]`. The UI then intersects `["*"]` with the tenant's enabled features, which yields `[]`, and `hasPermission` returns false. The super-admin sees an empty app.
- `handleSetCurrentView` in `App.tsx` still hand-rolls a check for only `'Super Admin'` and `'superadmin'`, bypassing the new helper.

**Fix:** Make `derivePermissionState` treat `'*'` in the delivered list as a super grant (skip the tenant intersection). Mirror the backend normalization (`lower().trim().replace(/[ -]/g, '_')`) in `isSuperAdminRoleName`, and have `handleSetCurrentView` call it.

### WR-08: D-26 cache hygiene covers only `omni_cache_roles`

**File:** `services/apiService.ts:131-134, 428-455`.

**Issue:** `clearSessionCaches()` removes only `omni_cache_roles`. `fetchWithCache` also writes `omni_cache_users`, `omni_cache_tenants` and `omni_cache_assets`, and `omni_cache_agents` is written elsewhere. These survive logout or session expiry in the same tab. The module-level `USERS`, `TENANTS`, `ASSETS` and `ROLES` variables survive too.

Any non-403 error (a 500, or the backend being offline) falls back to that cache. Tenant A's users and assets can then be shown to tenant B who signs in later in the same tab. The 403 branch removes the sessionStorage key but never resets the module variable via `updateLocalVar`, so the previous user's data stays in memory.

**Fix:** Clear every `omni_cache_*` key on logout and session expiry:

```ts
Object.keys(sessionStorage).filter(k => k.startsWith('omni_cache_')).forEach(k => sessionStorage.removeItem(k));
```

Also reset the module caches (`USERS = []` and so on), and call `updateLocalVar` with the empty value in the 403 branch.

## Info

### IN-01: `rbac_utils.require_role` and the `Permission` enum are dead and inconsistent

**File:** `backend/rbac_utils.py:27-60, 109-119`.

**Issue:**
- `require_role` here compares raw strings (`user.role not in allowed_roles`). `RBACService.require_role` normalizes. I found no importers of the `rbac_utils` version.
- The `Permission` enum holds a second vocabulary (`view:reports`, `manage:billing`, `view:ai`) that does not match the table. I found no `Permission.*` users.
- If it were ever used, the raw comparison would silently deny a `Tenant Admin` user against `["admin"]`.

**Fix:** Delete both, or make `require_role` delegate to the `RBACService` implementation.

### IN-02: Code placed between import blocks in `authentication_endpoints.py`

**File:** `backend/authentication_endpoints.py:5-24`.

**Issue:** `_SENSITIVE_USER_FIELDS`, `_SENSITIVE_KEY_RE` and `_public_user_fields` are defined between two import blocks (E402). The `token` fragment in `_SENSITIVE_KEY_RE` will also strip any benign user field that happens to contain it. That is acceptable as a denylist, but it should be a conscious choice.

**Fix:** Move the helper below the imports. Consider an allowlist of user fields for responses.

### IN-03: `session_permissions` swallows all exceptions and delivers defaults

**File:** `backend/rbac_service.py:87-92`.

**Issue:** The degrade-to-defaults behaviour is documented, but a role-store outage then shows users a different permission list from the one enforcement sees only in the failing window. Enforcement itself (`verify_permission`) is correct and fails closed. `session_permissions` logs a warning on each call, with no rate limiting.

**Fix:** None required; consider a metric or rate-limited log.

### IN-04: Archived `reset_db_fresh.py` is still a destructive, runnable script

**File:** `archive/backend-rbac-oneoffs/reset_db_fresh.py`.

**Issue:**
- The script drops and reseeds data. It falls back to placeholder passwords `changeme_set_SUPER_ADMIN_PASSWORD` and `changeme_set_TENANT_ADMIN_PASSWORD` when env vars are unset, so a casual run seeds known-weak credentials.
- `ARCHIVED.md` says "do not run", but the file is still executable Python.
- `fix_rbac_integrations.py` imports `database` and `tenant_context` and cannot resolve them from the new location. That makes it inert, which is good, but accidental.

**Fix:** Optionally strip the executable bit or add a top-of-file `raise SystemExit("archived")`. Verified: nothing outside `ARCHIVED.md` and `test_rbac_defaults.py` references these files.

### IN-05: `can_assign_role` table-only helper has no production caller

**File:** `backend/rbac_service.py:152-169`.

**Issue:** `RBACService.can_assign_role`, `get_permissions_for_role` and `default_roles` have no non-test callers in `backend/`. They duplicate the ceiling logic that `role_assignment.assert_can_assign_role` implements, so two implementations can drift.

**Fix:** Remove them or have `role_assignment` call into them.

---

_Reviewed: 2026-10-12_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
