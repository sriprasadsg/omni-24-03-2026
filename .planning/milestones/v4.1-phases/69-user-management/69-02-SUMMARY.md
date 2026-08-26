---
phase: 69-user-management
plan: "02"
subsystem: auth
tags: [rbac, fastapi, itam, permissions]

requires:
  - phase: 69-01
    provides: "User CRUD gated by itam_asset_endpoints._require_itam_admin (rbac_utils.verify_permission), role validated against rbac_service.default_roles via normalized comparison"
provides:
  - "rbac_service.default_roles: itam_admin/itam_user/itam_viewer ITAM-scoped roles"
  - "rbac_service.get_permissions_for_role(role) -> list[str] — sync, in-memory, for frontend UI role-matrix rendering"
  - "rbac_service.can_assign_role(caller_role, target_role) -> bool — super-admin-only guard for assigning super_admin"
  - "rbac_service._normalize_role() maps 'platform_admin' -> 'super_admin' (closes the platform-admin gap)"
  - "auth_roles.SUPER_ROLES includes both 'platform-admin' and 'platform_admin'"
  - "rbac_utils.is_super_admin()/verify_permission() route through rbac_service._normalize_role instead of a second hardcoded literal/exact-match set"
affects: [69-03-ldap, 69-04-sso, 70-core-data-audit-customization]

tech-stack:
  added: []
  patterns:
    - "Single normalization source of truth: rbac_service._normalize_role() is now the only place role-string canonicalization logic lives; rbac_utils.py and auth_roles.py delegate to or mirror it instead of maintaining independent normalization"

key-files:
  created: []
  modified:
    - backend/rbac_service.py
    - backend/auth_roles.py
    - backend/rbac_utils.py
    - backend/tests/test_rbac.py

key-decisions:
  - "Added a new sync method get_permissions_for_role(role: str) rather than overloading the plan's literally-named get_user_permissions(role), because RBACService already has an async get_user_permissions(self, user: TokenData) that queries the DB — Python has no signature-based overloading, so reusing the name would have silently shadowed the existing async DB-aware method."
  - "Fixed backend/rbac_utils.py even though it isn't in the plan's files_modified list: it is the actual enforcement path behind itam_asset_endpoints._require_itam_admin, which user_endpoints.py (64-01) reuses to admin-gate User CRUD. Its verify_permission() fallback did exact-string-match lookups with no normalization at all — leaving it untouched would mean the plan's own must_have truth ('Role normalization handles all variants consistently') stayed false for the actual code path enforcing ITAM admin access, and WINDOWS.md #6's reported bug (Title-Case 'Admin'/'User'/'Viewer' from role_endpoints.py's /api/roles stub resolving to zero permissions) would remain unfixed."
  - "Did not touch rbac_utils.require_role() (unused — grep confirms zero callers anywhere in backend/) and did not touch the ~100 individual endpoint files that each define a local `_SUPER_ROLES = {...}` literal set (webhook_endpoints.py, soar_endpoints.py, etc.) — consolidating those is a much larger refactor outside both this task's file scope and the specific reported pitfall."
  - "rbac_utils.verify_permission()'s DEFAULT_PERMISSIONS dict itself was left as-is (not merged with rbac_service.default_roles) — the two dicts have already drifted (different permission lists for 'admin'/'Tenant Admin'), and merging them would risk silently changing existing-role permissions in ~50 endpoint files that depend on this exact dict. Only the lookup-key normalization was fixed (Rule 1, narrow bug fix), not the underlying permission values (would be Rule 4 territory)."

requirements-completed: [ITAM-USR-02]

coverage:
  - id: D1
    description: "ITAM-specific roles (itam_admin, itam_user, itam_viewer) added to rbac_service.default_roles with correct permission tiers, enforced via has_permission()/require_role() dependency factories"
    requirement: "ITAM-USR-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_rbac.py::TestItamRoles (5 tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Role normalization pitfall fixed: 'platform-admin'/'platform_admin' both resolve to super_admin consistently across rbac_service, auth_roles.SUPER_ROLES, and rbac_utils"
    requirement: "ITAM-USR-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_rbac.py::test_role_normalization"
        status: pass
      - kind: unit
        ref: "backend/tests/test_rbac.py::TestRbacUtilsNormalization::test_is_super_admin_recognizes_platform_admin_underscore_variant"
        status: pass
    human_judgment: false
  - id: D3
    description: "WINDOWS.md #6 confirmed and fixed: Title-Case roles ('Admin'/'User'/'Viewer', as returned by role_endpoints.py's /api/roles stub) no longer resolve to zero permissions via rbac_utils.verify_permission's fallback path"
    requirement: "ITAM-USR-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_rbac.py::TestRbacUtilsNormalization::test_title_case_admin_resolves_permissions_not_empty"
        status: pass
      - kind: unit
        ref: "backend/tests/test_rbac.py::TestRbacUtilsNormalization::test_title_case_user_resolves_view_permissions"
        status: pass
      - kind: unit
        ref: "backend/tests/test_rbac.py::TestRbacUtilsNormalization::test_title_case_viewer_denied_manage_permission"
        status: pass
    human_judgment: false
  - id: D4
    description: "Only super-admins can assign the super-admin role (T-64-04); rbac_service.can_assign_role() helper added and tested (user_endpoints.py's existing 64-01 guard already enforced this at the endpoint level)"
    requirement: "ITAM-USR-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_rbac.py::TestCanAssignRole (3 tests)"
        status: pass
    human_judgment: false

duration: 40min
completed: 2026-08-13
status: complete
---

# Phase 69 Plan 02: RBAC extension with ITAM roles, fixed normalization, super-admin guard Summary

**Added itam_admin/itam_user/itam_viewer roles to rbac_service, closed the "platform-admin gap" in `_normalize_role()`, and fixed the WINDOWS.md #6 role-normalization bug in `rbac_utils.verify_permission()` that made the /api/roles UI's Title-Case "Admin"/"User"/"Viewer" resolve to zero permissions.**

## Performance

- **Duration:** ~40 min
- **Tasks:** 2
- **Files modified:** 4 (1 file — `rbac_utils.py` — added beyond the plan's listed 3, as a Rule 1/2 deviation)

## Accomplishments
- `rbac_service.default_roles` gained `itam_admin` (manage:assets/licenses/users/procurement/finance), `itam_user` (view + request:assets), `itam_viewer` (view-only)
- Added `rbac_service.get_permissions_for_role(role) -> list[str]` — a synchronous, DB-free lookup for frontend UI role-matrix rendering (the read-side contract `RoleEditorModal.tsx` needs, per 64-01's `<frontend_scope>` deferral note)
- Added `rbac_service.can_assign_role(caller_role, target_role) -> bool` — reusable super-admin-assignment guard (T-64-04); `user_endpoints.py`'s existing 64-01 inline guard already enforces the same rule at the endpoint
- Fixed `rbac_service._normalize_role()` to map `"platform_admin"` → `"super_admin"` — previously it normalized to the distinct key `"platform_admin"`, so `has_permission`/`require_role`/`get_user_permissions` did not recognize platform-admin callers as super-admins even though `auth_roles.SUPER_ROLES` already treated `"platform-admin"` as one (RESEARCH.md Pitfall 3)
- Added `"platform_admin"` (underscore) to `auth_roles.SUPER_ROLES`, since many callers across the codebase do a raw `role in SUPER_ROLES` membership check without normalizing first
- Fixed `rbac_utils.is_super_admin()` to delegate entirely to `rbac_service._normalize_role()` instead of maintaining a second hardcoded literal set
- Fixed `rbac_utils.verify_permission()`'s `DEFAULT_PERMISSIONS` fallback to normalize the lookup key when the raw role string isn't found verbatim — closing the exact bug WINDOWS.md #6 reported (confirmed via a failing test before the fix, passing after)
- 28 tests in `test_rbac.py` (6 pre-existing + 22 new), full backend suite: 1948 passed / 35 skipped / 3 pre-existing unrelated failures (`test_agentic_ai` tool_choice kwarg, `test_e2e_integration` golden path, `test_rust_heartbeat_parity` agent_type field) — same baseline failures as 64-01, no new regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend RBAC with ITAM-specific roles and permissions** - `7200b688` (feat) — includes the `_normalize_role` platform_admin fix, bundled in the same file edit
2. **Task 2: Fix role normalization pitfall in auth_roles.py** - `c797ea1d` (fix) — `auth_roles.py` + `rbac_utils.py` (deviation)

## Files Created/Modified
- `backend/rbac_service.py` - ITAM roles, `get_permissions_for_role`, `can_assign_role`, `_normalize_role` platform_admin fix
- `backend/auth_roles.py` - `SUPER_ROLES` gains `"platform_admin"` (underscore)
- `backend/rbac_utils.py` - `is_super_admin`/`verify_permission` normalization consolidated through `rbac_service._normalize_role` (deviation, see below)
- `backend/tests/test_rbac.py` - 22 new tests: ITAM roles, `get_permissions_for_role`, `can_assign_role`, `test_role_normalization`, `TestRbacUtilsNormalization`

## Decisions Made
- New sync helper named `get_permissions_for_role(role: str)` rather than reusing the plan's literal `get_user_permissions(role)` name, to avoid shadowing the existing async DB-aware `get_user_permissions(self, user: TokenData)`.
- Extended scope to `backend/rbac_utils.py` (not in the plan's `files_modified`) because it is the actual runtime enforcement path for ITAM admin gating (`itam_asset_endpoints._require_itam_admin` → `rbac_utils.verify_permission`), and leaving it unfixed would mean the plan's core "no platform-admin gap" / "role normalization handles all variants" truths remained false for real request traffic. This directly resolves WINDOWS.md #6.
- Left `rbac_utils.require_role()` untouched (zero callers anywhere in `backend/`, confirmed via grep) and left the ~100 per-endpoint-file local `_SUPER_ROLES` literal sets untouched — both are out of this plan's specific reported pitfall and would be a much larger, higher-risk refactor.
- Did not merge `rbac_utils.DEFAULT_PERMISSIONS` with `rbac_service.default_roles` — the two dicts have already drifted with different permission lists for the same role names; only the lookup-key normalization was fixed, not the underlying values, to avoid silently changing existing permissions across ~50 dependent endpoint files.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `rbac_utils.verify_permission()` resolved Title-Case roles to zero permissions (WINDOWS.md #6)**
- **Found during:** Task 2, while tracing the "single normalization path" instruction to its actual runtime enforcement point
- **Issue:** `role_endpoints.py`'s `/api/roles` stub (the frontend's actual role-selection UI) returns `"Admin"`/`"User"`/`"Viewer"` (Title-Case). `rbac_utils.verify_permission()` — the function behind `itam_asset_endpoints._require_itam_admin`, which 64-01's User CRUD reuses for admin gating — did an exact-string-match lookup against its `DEFAULT_PERMISSIONS` dict (keys `"admin"`/`"user"`/`"viewer"`, lowercase). A user with role `"Admin"` therefore resolved to `[]` permissions, i.e. `manage:assets`-gated endpoints (including `POST /api/users`) would 403 the UI's own default admin role.
- **Fix:** Normalize the lookup key through `rbac_service._normalize_role()` when the raw role string isn't found verbatim in `DEFAULT_PERMISSIONS`, preserving the existing `tenant_admin`/`Analyst` canonical-key redirects.
- **Files modified:** `backend/rbac_utils.py`
- **Verification:** `TestRbacUtilsNormalization::test_title_case_admin_resolves_permissions_not_empty` reproduced the bug (failed) before the fix and passes after; `test_lowercase_admin_behavior_unchanged` and `test_tenant_admin_snake_case_still_redirects_to_canonical_entry` pin that prior behavior is preserved.
- **Committed in:** `c797ea1d` (Task 2 commit)

**2. [Rule 1 - Bug] `rbac_utils.is_super_admin()` used a second, incomplete hardcoded role set**
- **Found during:** Task 2, same investigation as above
- **Issue:** `is_super_admin()` compared against a local `_SUPER_ADMIN_ROLES` frozenset that (like `auth_roles.SUPER_ROLES` before this plan) was missing the underscore `"platform_admin"` variant, and duplicated normalization logic that could drift from `rbac_service._normalize_role()`.
- **Fix:** Delegate entirely to `rbac_service._normalize_role(role) == "super_admin"`.
- **Files modified:** `backend/rbac_utils.py`
- **Verification:** `TestRbacUtilsNormalization::test_is_super_admin_recognizes_platform_admin_underscore_variant`
- **Committed in:** `c797ea1d` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 — bugs in the actual RBAC enforcement path that this plan's stated objective explicitly targets)
**Impact on plan:** Both fixes were necessary for the plan's must-have truth ("Role normalization handles all variants consistently, no platform-admin gap") to hold for real request traffic, not just for `rbac_service.py`'s own dependency factories. No architectural changes — same file, same dict shapes, only the key-lookup normalization changed. Confirmed resolves the exact case WINDOWS.md #6 reported.

## Issues Encountered
None beyond the deviations documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `rbac_service.default_roles` now has ITAM-scoped roles (`itam_admin`/`itam_user`/`itam_viewer`) ready for 64-03 (LDAP) and 64-04 (SSO) to assign to synced users.
- `get_permissions_for_role()` is the read-side contract `RoleEditorModal.tsx` needs; wiring it into an endpoint (and building `saveRole()`'s real persistence, still a mock per 64-01) remains explicitly deferred to a future plan, per 64-01's `<frontend_scope>` reasoning (`services/apiService.ts` is owned by Phase 70).
- `role_endpoints.py`'s `/api/roles` stub itself is unchanged — it still returns a static 3-role list uncorrelated with `rbac_service.default_roles`'s full role set (including the new ITAM roles and `Tenant Admin`). Normalization now makes whatever it returns resolve correctly, but the stub's role catalog is still incomplete; flagging for whoever wires the roles UI to the backend.
- Full backend suite: 1948 passed / 35 skipped / 3 pre-existing unrelated failures (unchanged from 64-01's baseline) — confirms no regressions from the normalization consolidation.

---
*Phase: 64-user-management*
*Completed: 2026-08-13*

## Self-Check: PASSED

- FOUND: backend/rbac_service.py
- FOUND: backend/auth_roles.py
- FOUND: backend/rbac_utils.py
- FOUND: backend/tests/test_rbac.py
- FOUND: commit 7200b688 (Task 1)
- FOUND: commit c797ea1d (Task 2)
