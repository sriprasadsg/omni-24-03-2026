---
phase: 64-user-management
plan: "01"
subsystem: auth
tags: [fastapi, mongodb, rbac, tenant-isolation, pydantic]

requires:
  - phase: 56-63 (ITAM Console phases)
    provides: "_require_itam_admin admin-gating pattern (itam_asset_endpoints.py), rbac_service.default_roles, auth_utils bcrypt helpers"
provides:
  - "User CRUD (create/read/update/delete/list) with ITAM fields: tenantId, role, status, createdAt, updatedAt, lastLogin"
  - "GET /api/users/me — self-profile endpoint, not admin-gated"
  - "GET /api/users pagination (skip/limit), filtering (role/status/tenantId), search (email/full_name), X-Total-Count header"
  - "Tenant-exists validation on user create/tenant-move"
  - "Role validation against rbac_service.default_roles (normalized)"
affects: [64-02-rbac, 64-03-ldap, 65-core-data-audit-customization]

tech-stack:
  added: []
  patterns:
    - "Admin gating via itam_asset_endpoints._require_itam_admin (imported, not re-implemented) — matches ITAM phases 56-63 convention"
    - "Lifecycle status stored Title-Case ('Active'/'Inactive'/'Pending') to match authentication_endpoints.py's existing signup/refresh-token convention; API response collapses to the frontend's strict 'Active'|'Disabled' two-value contract"

key-files:
  created:
    - backend/tests/test_user_crud.py
  modified:
    - backend/user_endpoints.py

key-decisions:
  - "Reused itam_asset_endpoints._require_itam_admin (checks manage:assets) for all admin-gated CRUD endpoints instead of the file's old local role-string check, per plan instruction to follow the ITAM phases 56-63 pattern"
  - "Role validation compares rbac_service._normalize_role(input) against normalized rbac_service.default_roles keys, not exact-string match — the shipped /api/roles UI stub returns Title-Case names ('Admin', 'User', 'Viewer') that don't literally match rbac_service's lowercase keys; normalized comparison satisfies the plan's literal validation requirement without rejecting the UI's actual default role selection"
  - "Lifecycle status stored as Title-Case 'Active'/'Inactive'/'Pending' (not the plan's literal lowercase wording) because authentication_endpoints.py's signup flow already writes status:'Active' and its refresh-token endpoint gates on status != 'Active' — a lowercase value would have silently broken refresh tokens for every user created/edited through this router"
  - "GET /api/users pagination metadata via X-Total-Count header, not a wrapped {items,total} body — keeps the default (unparameterized) response a bare JSON array, which services/apiService.ts fetchUsers() requires"
  - "createdAt/updatedAt/lastLogin exposed camelCase (replacing the old snake_case created_at key) to match the ITAM data convention and authentication_endpoints.py's own signup-created field names; nothing in the frontend types.ts User type or apiService.ts read created_at, so the rename is safe"

requirements-completed: [ITAM-USR-01]

coverage:
  - id: D1
    description: "User CRUD (create/read/update/delete) works for ITAM-scoped users with tenantId, role, status fields"
    requirement: "ITAM-USR-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_user_crud.py::TestCreateUser (8 tests)"
        status: pass
      - kind: unit
        ref: "backend/tests/test_user_crud.py::TestUpdateUser (4 tests)"
        status: pass
      - kind: unit
        ref: "backend/tests/test_user_crud.py::TestDeleteUser (3 tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Tenant isolation enforced on list/update/delete; admin gating via _require_itam_admin; role validated against rbac_service.default_roles"
    requirement: "ITAM-USR-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_user_crud.py::TestTenantIsolation (2 tests)"
        status: pass
      - kind: unit
        ref: "backend/tests/test_user_crud.py::TestCreateUser::test_non_admin_cannot_create_user"
        status: pass
    human_judgment: false
  - id: D3
    description: "GET /api/users/me returns the caller's own profile without admin gating"
    requirement: "ITAM-USR-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_user_crud.py::TestUserProfile::test_get_my_profile_does_not_require_admin"
        status: pass
    human_judgment: false
  - id: D4
    description: "GET /api/users pagination, role/status/tenantId filtering, and email/name search, with the unparameterized call still returning a bare JSON array"
    requirement: "ITAM-USR-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_user_crud.py::test_user_list_pagination"
        status: pass
      - kind: unit
        ref: "backend/tests/test_user_crud.py::TestListUsersFilteringAndSearch (6 tests)"
        status: pass
    human_judgment: false

duration: 55min
completed: 2026-08-13
status: complete
---

# Phase 64 Plan 01: User CRUD with ITAM fields Summary

**Extended `user_endpoints.py`'s User CRUD with tenant-validated `tenantId`, `rbac_service`-checked `role`, a lifecycle `status` field, and pagination/filtering — gated by the canonical `_require_itam_admin` dependency reused from `itam_asset_endpoints.py`.**

## Performance

- **Duration:** 55 min
- **Tasks:** 2
- **Files modified:** 2 (1 modified, 1 created)

## Accomplishments
- User CRUD (`GET/POST /api/users`, `PUT/DELETE /api/users/{id}`) now carries `tenantId` (required, validated against `db.tenants`), `role` (validated against `rbac_service.default_roles`, normalized), and a `status` lifecycle field (`active`/`inactive`/`pending`)
- All CRUD endpoints gated via `itam_asset_endpoints._require_itam_admin` (imported, not duplicated) instead of the file's old ad-hoc role-string allowlist
- New `GET /api/users/me` — any authenticated user reads their own profile, no admin gate
- `GET /api/users` gained `skip`/`limit` pagination, `role`/`status`/`tenantId`/`search` filters, and an `X-Total-Count` response header, while the unparameterized call still returns a bare JSON array (verified by an explicit regression test)
- Fixed two pre-existing bugs found while extending this exact code path (see Deviations)

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend User CRUD with ITAM fields and admin gating (tracer)** - `9ba82ab1` (feat)
2. **Task 2: Add user listing with pagination and filtering** - `dde70b75` (feat)

**Plan metadata:** (this commit)

## Files Created/Modified
- `backend/user_endpoints.py` - User CRUD extended with ITAM fields, tenant/role validation, admin gating, pagination/filtering
- `backend/tests/test_user_crud.py` - CRUD, tenant isolation, admin gating, role/status validation, `/me` profile, pagination/filter/search tests (25 tests)

## Decisions Made
- Reused `itam_asset_endpoints._require_itam_admin` for admin gating on all CRUD endpoints (list/create/update/delete), matching the plan's explicit instruction to follow the ITAM phases 56-63 pattern. `GET /api/users/me` intentionally does not use it (self-service read).
- Role validation normalizes both the input and `rbac_service.default_roles` keys via `rbac_service._normalize_role` before comparing, rather than exact-string match — see Deviations for why this was necessary to avoid breaking the shipped UI's default flow.
- Lifecycle `status` is stored Title-Case (`Active`/`Inactive`/`Pending`) rather than the plan's literal lowercase wording — see Deviations for the cross-file grounding that drove this.
- Pagination metadata surfaces via `X-Total-Count` header (not a wrapped `{items,total}` body), keeping the default response a bare array per the plan's `<frontend_scope>` constraint.
- `createdAt`/`updatedAt`/`lastLogin` (camelCase) replace the old `created_at` response key, matching `authentication_endpoints.py`'s own signup-created field names and the broader ITAM data convention; read paths fall back to legacy `created_at`/`is_active` for pre-existing documents.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `create_user` imported a function that does not exist**
- **Found during:** Task 1, while extending `create_user`
- **Issue:** The pre-existing code did `from authentication_endpoints import _validate_password_complexity` inside `create_user`. No such name exists in `authentication_endpoints.py` (only `auth_utils.validate_password_complexity`, no underscore, no re-export). Every call to `POST /api/users` would raise `ImportError` and 500.
- **Fix:** Replaced with a module-level `from auth_utils import ... validate_password_complexity` import and call.
- **Files modified:** `backend/user_endpoints.py`
- **Verification:** `TestCreateUser::test_create_user_weak_password_rejected` and `test_create_user_with_itam_fields` both exercise this path.
- **Committed in:** `9ba82ab1` (Task 1 commit)

**2. [Rule 1 - Bug] Admin-created users had no working refresh-token path**
- **Found during:** Task 1, while designing the new `status` field
- **Issue:** `authentication_endpoints.py`'s `/api/auth/signup` writes `"status": "Active"` on every new user, and its `/refresh-token` endpoint gates on `user.get("status") != "Active"`. The pre-existing `create_user` in this file never set a `status` field at all (only `is_active: True`), so any user created via the admin CRUD endpoint would fail refresh-token validation. The plan's literal wording ("status field active/inactive/pending, default 'active'", lowercase) would have reproduced this bug with a case mismatch instead of fixing it.
- **Fix:** Store `status` Title-Case (`Active`/`Inactive`/`Pending`, matching the signup convention exactly) as the canonical field; accept case-insensitive `active`/`inactive`/`pending` input and normalize on write. The outward JSON response still exposes the frontend's required two-value `'Active'|'Disabled'` contract via a separate display mapping, so `SettingsUsersTab.tsx`/`apiService.ts` are unaffected.
- **Files modified:** `backend/user_endpoints.py`
- **Verification:** `TestCreateUser::test_create_user_with_itam_fields` asserts the stored doc has `status: "Active"`; `TestUpdateUser::test_update_user_role_and_status` asserts `inactive` input normalizes to stored `"Inactive"` while the API response still shows `"Disabled"`.
- **Committed in:** `9ba82ab1` (Task 1 commit)

**3. [Rule 1 - Bug] Role-assignment check rejected the UI's own default role**
- **Found during:** Task 1, while implementing rbac_service-backed role validation
- **Issue:** The frontend's `AddUserModal.tsx` populates its role `<select>` from `GET /api/roles` (`role_endpoints.py`), a static stub returning Title-Case names (`"Admin"`, `"User"`, `"Viewer"`) that don't include `"Tenant Admin"` at all — so its `roles[0]` default is `"Admin"`. The pre-existing `_ASSIGNABLE_ROLES` set only contained lowercase `"admin"`, so a non-super-admin caller creating a user with the UI's own default role selection (`"Admin"`) would get a 403 today.
- **Fix:** Role validation now normalizes both the requested role and `rbac_service.default_roles`' keys via `rbac_service._normalize_role` before comparing, so `"Admin"` → `"admin"` matches correctly. Added a regression test (`test_create_user_title_case_admin_role_accepted`) pinning this.
- **Files modified:** `backend/user_endpoints.py`
- **Verification:** `TestCreateUser::test_create_user_title_case_admin_role_accepted`
- **Committed in:** `9ba82ab1` (Task 1 commit)

---

**Total deviations:** 3 auto-fixed (all Rule 1 — bugs directly in the `create_user`/`update_user` code this task rewrote)
**Impact on plan:** All three fixes were necessary for the extended CRUD to actually work end-to-end; none expand scope beyond `backend/user_endpoints.py`. No architectural changes.

## Known Follow-ups (Not Fixed — Out of Scope)

Discovered during this task but explicitly NOT fixed here, since they reach outside `backend/user_endpoints.py`/`backend/tests/test_user_crud.py` (this plan's `files_modified`) and are either already tracked or belong to a later plan in this phase:

1. **`services/apiService.ts` `updateUser()` drops the `status` field.** `EditUserModal.tsx` already builds `{ role, status }` update payloads and its "Status" dropdown is fully wired in the UI, but `apiService.updateUser()`'s payload construction only forwards `{ full_name, role, password }` — `status` is silently discarded before the request is sent. The backend now fully supports `status` in `PUT /api/users/{id}` (this plan), but the shipped disable/enable-user UI flow remains non-functional until `apiService.ts` forwards it. Per this plan's `<frontend_scope>`, `services/apiService.ts` is owned by Phase 65; flagging here rather than fixing.
2. **System-wide role-casing inconsistency (`role_endpoints.py` vs. `rbac_service.py`/`auth_utils.py`) is unresolved.** `role_endpoints.py`'s `/api/roles` stub returns roles (`"Admin"`, `"User"`, `"Viewer"`) that do not correspond to any seeded `db.roles` document (only `"Super Admin"` and `"Tenant Admin"` are seeded at signup, per `app_startup.py`) and are absent from `auth_utils.DEFAULT_PERMISSIONS`'s exact-match fallback keys. A user created with role `"Admin"` (the UI's actual default) currently resolves to **zero permissions** via `rbac_utils.verify_permission`'s fallback path, independent of anything this plan touched. This plan's normalized role-validation fix prevents the CRUD *rejection* bug (#3 above) but does not touch the deeper permission-resolution gap — that is RESEARCH.md's flagged "Pitfall 3: Role Normalization Inconsistency" and is very likely the subject of 64-02 (ITAM-USR-02: RBAC). Flagging explicitly so 64-02 doesn't have to rediscover it.
3. **Signup-created vs. admin-created user documents still use inconsistent field names for password/name** (`password`/`name` from `/api/auth/signup` vs. `hashed_password`/`full_name` from this router). Both are already tolerated by the read paths this plan touched (`_to_response`, login's `stored_hash = user.get('password') or user.get('hashed_password')`), so this is not a functional bug, just noted for awareness — unifying it would be a Rule 4 architectural change outside this task's scope.

## Issues Encountered
None beyond the deviations documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `GET/POST/PUT/DELETE /api/users` and `GET /api/users/me` are live, tenant-isolated, and admin-gated — ready for 64-02 (RBAC) to build on top of, and for 64-03/64-04 (LDAP/SSO) to write into the same `users` collection shape.
- Flagged follow-ups above (especially #2, the role-casing/permission-resolution gap) should be read by whoever picks up 64-02.
- Full backend suite: 1929 passed / 35 skipped / 3 pre-existing unrelated failures (`test_agentic_ai` tool_choice kwarg, `test_e2e_integration` golden path, `test_rust_heartbeat_parity` agent_type field) — unchanged from the pre-existing baseline, confirming no regressions.

---
*Phase: 64-user-management*
*Completed: 2026-08-13*

## Self-Check: PASSED

- FOUND: backend/user_endpoints.py
- FOUND: backend/tests/test_user_crud.py
- FOUND: .planning/milestones/v4.1-phases/64-user-management/64-01-SUMMARY.md
- FOUND: commit 9ba82ab1 (Task 1)
- FOUND: commit dde70b75 (Task 2)
