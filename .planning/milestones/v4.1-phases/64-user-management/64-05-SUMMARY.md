---
phase: 64-user-management
plan: "05"
subsystem: auth
tags: [fastapi, mongodb, bcrypt, api-tokens, rbac, itam]

requires:
  - phase: 64-01
    provides: "User CRUD (db.users documents with email/role/tenantId), get_current_user session auth"
  - phase: 64-02
    provides: "rbac_service.default_roles ITAM roles (itam_admin/itam_user/itam_viewer), _normalize_role, itam_asset_endpoints._require_itam_admin admin-gating pattern"
provides:
  - "backend/api_key_auth.py: APIKeyModel/APIKeyService — user-scoped API token lifecycle (create/list/revoke/validate/authenticate), bcrypt-hashed storage, prefix lookup, expiration, per-key in-process rate limiting"
  - "backend/api_key_endpoints.py: /api/api-keys (user-scoped create/list/revoke/scopes catalog) and /api/admin/api-keys (admin cross-tenant list/revoke)"
  - "auth_types.TokenData.scopes (Optional[List[str]], default None) and .auth_source (default 'session') — appended fields, fully backward compatible"
  - "rbac_service._scopes_allow / has_permission() / require_role() — scope-narrowing enforcement: a token's scopes can only narrow its owner's role, never widen it"
affects: [65-core-data-audit-customization]

tech-stack:
  added: []
  patterns:
    - "User-scoped API tokens stored as users.apiKeys array (mirrors the pre-existing tenants.apiKeys shape used by tenant_endpoints.py's legacy tenant-scoped keys) — two independent key mechanisms coexist by design, both authenticate via get_current_user_or_api_key"
    - "TokenData.scopes/auth_source is the general-purpose scope-narrowing primitive: has_permission()/require_role() resolve role permissions first (outer bound), then apply scope intersection second — any future scoped-credential type (not just API keys) can reuse this by setting these two fields"

key-files:
  created:
    - backend/api_key_endpoints.py
    - backend/tests/test_api_key.py
  modified:
    - backend/api_key_auth.py
    - backend/auth_types.py
    - backend/rbac_service.py
    - backend/router_registry.py
    - backend/tests/test_api_key_auth.py

key-decisions:
  - "auth_types.py's TokenData field addition (scopes/auth_source) was committed as part of Task 1, not Task 3, even though the plan's frontmatter lists it under Task 3's files_modified — Task 1's own action step 4 requires api_key_auth.authenticate() to construct a scope-carrying TokenData, which is impossible without the fields existing first. The fields are purely additive defaults (no behavior change on their own); the actual enforcement logic (rbac_service.py) remained in Task 3 as specified."
  - "get_current_user_or_api_key tries the new user-scoped token path first, then falls back unchanged to the pre-existing tenant-scoped lookup (tenants.apiKeys.keyHash) — both mechanisms authenticate through the same dependency so already-issued tenant-scoped keys keep working with zero migration."
  - "_scopes_allow() and require_role()'s scope-gating branch use getattr()+isinstance(list) rather than a bare `user.scopes is None` check, specifically to stay inert against the large existing test corpus that injects the current-user dependency as a bare unittest.mock.MagicMock() (not a real TokenData) — attribute access on those doubles auto-vivifies a truthy child Mock instead of None or a real list, which a naive None-check would have misread as 'scope-restricted'. Confirmed via a full-suite regression run before this was caught (see Deviations)."
  - "Admin-equivalent scope gating in require_role() uses a module-level role->scope map (admin/tenant_admin/super_admin/itam_admin -> admin:itam) rather than a single hardcoded scope name, per the plan's explicit instruction, keeping room for future role-specific gating scopes without touching the enforcement code."

requirements-completed: [ITAM-USR-05]

coverage:
  - id: D1
    description: "Full API token lifecycle: create (returns plaintext once), list (excludes hash), revoke, bcrypt-hashed storage, prefix-based lookup"
    requirement: "ITAM-USR-05"
    verification:
      - kind: unit
        ref: "backend/tests/test_api_key.py::TestAPIKeyServiceLifecycle (11 tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Token expiration and per-key rate limiting enforced at validation time"
    requirement: "ITAM-USR-05"
    verification:
      - kind: unit
        ref: "backend/tests/test_api_key.py::TestAPIKeyServiceLifecycle::test_expired_key_fails_validation"
        status: pass
      - kind: unit
        ref: "backend/tests/test_api_key.py::TestAPIKeyServiceLifecycle::test_rate_limit_enforced_per_key"
        status: pass
    human_judgment: false
  - id: D3
    description: "User-facing /api/api-keys (create/list/revoke/scopes) and admin /api/admin/api-keys (cross-tenant list/revoke) endpoints, wired into the app via router_registry.py"
    requirement: "ITAM-USR-05"
    verification:
      - kind: unit
        ref: "backend/tests/test_api_key.py::TestAPIKeyEndpoints (7 tests)"
        status: pass
    human_judgment: false
  - id: D4
    description: "TokenData carries scopes/auth_source with backward-compatible defaults; rbac_service intersects token scopes with role permissions (has_permission/require_role) — a key can only narrow its owner's role, never widen it, including for super_admin wildcard roles"
    requirement: "ITAM-USR-05"
    verification:
      - kind: unit
        ref: "backend/tests/test_api_key.py::TestTokenDataDefaults (2 tests)"
        status: pass
      - kind: unit
        ref: "backend/tests/test_api_key.py::TestScopeEnforcement (7 behavior tests)"
        status: pass
      - kind: unit
        ref: "backend/tests/test_rbac.py + backend/tests/test_user_crud.py (54 tests, regression gate)"
        status: pass
    human_judgment: false

duration: ~50min
completed: 2026-08-12
status: complete
---

# Phase 64 Plan 05: API token management — lifecycle, scopes, expiration, rate limits Summary

**User-scoped API tokens (`APIKeyService` in `api_key_auth.py`) with bcrypt-hashed storage, expiration, and per-key rate limits, exposed via `/api/api-keys` + admin `/api/admin/api-keys`, and made genuinely scope-aware end-to-end: `rbac_service.has_permission()`/`require_role()` now intersect a token's scopes with its owner's role permissions instead of trusting the role alone.**

## Performance

- **Duration:** ~50 min
- **Tasks:** 3
- **Files modified:** 7 (2 created, 5 modified)

## Accomplishments
- Extended the 32-line `api_key_auth.py` X-API-Key stub into a full user-scoped token lifecycle: `APIKeyService.create_key/list_keys/revoke_key/validate_key/authenticate`, bcrypt-hashed storage (reusing `auth_utils.hash_password`/`verify_password`, not passlib — matches CLAUDE.md's dependency-reuse instruction), prefix-based lookup, expiration, and a per-key sliding-60s-window rate limiter
- `get_current_user_or_api_key` now tries the new user-scoped path first and falls back unchanged to the pre-existing tenant-scoped mechanism (`tenants.apiKeys`), so already-issued tenant keys (created via `tenant_endpoints.py`, consumed by `SettingsApiKeysTab.tsx`) keep authenticating with zero migration
- New `backend/api_key_endpoints.py`: user-scoped `POST/GET /api/api-keys`, `DELETE /api/api-keys/{id}`, `GET /api/api-keys/scopes`, and admin `GET/DELETE /api/admin/api-keys` gated by the canonical `itam_asset_endpoints._require_itam_admin`; registered in `router_registry.py`
- `auth_types.TokenData` gained `scopes: Optional[List[str]] = None` and `auth_source: str = "session"` — additive, backward-compatible fields
- `rbac_service.py`'s `has_permission()`/`require_role()` intersect role permissions with token scopes: role is the outer bound (a key can never exceed its owner's role), scopes only narrow, and a super_admin's `"*"` wildcard is still narrowed by an api_key token's scopes while a session super_admin is unrestricted
- Fixed a real regression this task introduced and caught before commit (see Deviations): the scope check initially used `user.scopes is None`, which broke ~30 pre-existing tests across `test_cloud_accounts.py`/`test_iac_scanner.py`/`test_program_service.py`/`test_container_sbom_export.py` that inject a bare `MagicMock()` as the current user

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend api_key_auth.py with full token lifecycle and scoping** - `75e7dc2e` (feat)
2. **Task 2: Create user-facing API token management endpoints** - `ca6d5659` (feat)
3. **Task 3: Make TokenData and rbac_service scope-aware** - `b186ee3b` (feat)

**Plan metadata:** (this commit)

## Files Created/Modified
- `backend/api_key_auth.py` - `APIKeyModel`/`APIKeyService` (create/list/revoke/validate/authenticate, bcrypt, prefix lookup, expiration, rate limit); `get_current_user_or_api_key` tries the new path first, falls back to the legacy tenant-scoped lookup unchanged
- `backend/api_key_endpoints.py` - new file: user-scoped and admin-scoped `/api/api-keys` routes
- `backend/auth_types.py` - `TokenData` gains `scopes`/`auth_source` (backward-compatible defaults)
- `backend/rbac_service.py` - `_scopes_allow()` helper; `has_permission()`/`require_role()` intersect role permissions with token scopes
- `backend/router_registry.py` - registers `api_key_endpoints.router` and `.admin_router`
- `backend/tests/test_api_key.py` - new file: 27 tests across lifecycle, endpoints, TokenData defaults, and scope-enforcement behavior
- `backend/tests/test_api_key_auth.py` - 3 pre-existing dependency tests updated to mock `db.users` (see Deviations)

## Decisions Made
- `auth_types.py`'s `TokenData` field addition landed in Task 1's commit rather than Task 3's, since Task 1's own action explicitly requires `api_key_auth.authenticate()` to build a scope-carrying `TokenData` — the fields are a compile-time prerequisite for Task 1's code, not enforcement logic (enforcement stayed in Task 3 as specified). Purely additive defaults; no behavior changes from this alone.
- `get_current_user_or_api_key` tries user-scoped tokens first, then the legacy tenant-scoped mechanism, rather than replacing it — the plan's `<frontend_scope>` explicitly requires the tenant-scoped routes to keep working unmodified.
- Scope-narrowing checks (`_scopes_allow`, `require_role`'s admin-gating branch) use `getattr(...) ` + an `isinstance(scopes, list)` guard instead of a literal `user.scopes is None` check, specifically so bare `MagicMock()` user doubles used throughout the pre-existing test suite are treated as "not scope-restricted" rather than accidentally scope-denied (see Deviations — this was caught by a full-suite run, not the plan's own `<verify>` commands, which only exercise the new/changed files).
- Admin-equivalent scope gating in `require_role()` uses a module-level `{role: scope}` map (`admin`/`tenant_admin`/`super_admin`/`itam_admin` → `admin:itam`) per the plan's instruction, rather than a single hardcoded scope string.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] New `api_key_endpoints.py` router was never mounted**
- **Found during:** Task 2
- **Issue:** A newly created FastAPI router file is not automatically wired into the app; without registration in `router_registry.py`, every route in `api_key_endpoints.py` would be unreachable (404) despite being fully implemented and tested at the function level.
- **Fix:** Added `_load(app, "api_key_endpoints", "router")` and `_load(app, "api_key_endpoints", "admin_router")` to `router_registry.py`, following the existing `_load(app, module, attr)` convention used by every other ITAM router.
- **Files modified:** `backend/router_registry.py`
- **Verification:** `python -c "import router_registry"` succeeds; `api_key_endpoints.router.prefix == "/api/api-keys"` and `.admin_router.prefix == "/api/admin/api-keys"` confirmed via direct import.
- **Committed in:** `ca6d5659` (Task 2 commit)

**2. [Rule 1 - Bug] `get_current_user_or_api_key`'s new db.users lookup broke 3 pre-existing dependency tests**
- **Found during:** Task 1, caught by a full-suite regression run (not the plan's own targeted `<verify>` commands)
- **Issue:** `test_api_key_auth.py`'s `test_dependency_valid_key_returns_tenant_scoped_api_integration`, `test_dependency_wrong_key_401`, and `test_dependency_revoked_key_401` mock `mongodb.db` with only a `tenants` collection configured. This task's change makes `get_current_user_or_api_key` query `db.users` first (the new user-scoped token path) before falling back to the tenant-scoped lookup — on these tests' mocks, `db.users` is an unconfigured `MagicMock` attribute, so `await db.users.find_one(...)` raised `TypeError: object MagicMock can't be used in 'await' expression`.
- **Fix:** Added an explicit empty `users=_col()` collection (which defaults `find_one` to an `AsyncMock` returning `None`) to those three tests' `_db(...)` mock construction, so the new lookup correctly resolves to "no user-scoped key found" and falls through to the existing tenant-scoped assertions unchanged.
- **Files modified:** `backend/tests/test_api_key_auth.py`
- **Verification:** `pytest backend/tests/test_api_key_auth.py -q` — 12/12 pass.
- **Committed in:** `75e7dc2e` (Task 1 commit)

**3. [Rule 1 - Bug] Naive `user.scopes is None` scope check broke ~30 pre-existing tests using bare `MagicMock()` user doubles**
- **Found during:** Task 3, caught by a full-suite regression run
- **Issue:** The plan's literal spec for `_scopes_allow` ("returns True when `user.scopes` is None") was implemented as a direct attribute check. Many pre-existing test files (`test_cloud_accounts.py`, `test_iac_scanner.py`, `test_program_service.py`, `test_container_sbom_export.py`) inject the `get_current_user` dependency as a bare `unittest.mock.MagicMock()`, not a real `TokenData`. Accessing `.scopes` on such a mock auto-vivifies a truthy child `MagicMock` rather than returning `None`, so `_scopes_allow` incorrectly treated every one of those requests as scope-restricted-with-no-matching-scope, turning previously-200 responses into 403s (~30 test failures across those 4 files, confirmed via a before/after full-suite diff isolating the change to `rbac_service.py`).
- **Fix:** Changed the check to `getattr(user, "scopes", None)` combined with an explicit `isinstance(scopes, list)` guard — a bare Mock's auto-vivified attribute fails the `isinstance` check and is treated as unrestricted (matching real session `TokenData` behavior), while a genuine empty-or-populated `list` (only ever produced by real `TokenData` instances, including this task's own `authenticate()`) is correctly scope-checked. Applied the same defensive pattern to `require_role()`'s `auth_source`/scope reads.
- **Files modified:** `backend/rbac_service.py`
- **Verification:** `pytest backend/tests/test_cloud_accounts.py backend/tests/test_iac_scanner.py backend/tests/test_program_service.py backend/tests/test_container_sbom_export.py backend/tests/test_api_key.py backend/tests/test_rbac.py backend/tests/test_user_crud.py -q` — 136/136 pass; full backend suite confirms only the 3 pre-existing unrelated failures remain.
- **Committed in:** `b186ee3b` (Task 3 commit)

---

**Total deviations:** 3 auto-fixed (1 Rule 3 — blocking wiring gap, 2 Rule 1 — bugs this task's own changes introduced and caught before commit via full-suite regression runs)
**Impact on plan:** All three fixes were necessary for the plan's must-haves to hold for real traffic and for the existing test suite to stay green. No architectural changes; no scope creep beyond making this task's own new code work correctly against the rest of the codebase.

## Issues Encountered
None beyond the deviations documented above.

## User Setup Required
None - no external service configuration required. Note: the in-process rate limiter (`api_key_auth._usage_windows`) is a single-worker, in-memory sliding window — matches the same documented tradeoff RESEARCH.md flags for `mfa_service.py`'s session store (Pitfall 1). A multi-worker production deployment would need a shared store (e.g. Redis); not required for this plan's scope.

## Next Phase Readiness
- `TokenData.scopes`/`.auth_source` and `rbac_service`'s scope-intersection logic are general-purpose — any future scoped-credential type can reuse them by populating the two fields, not just API keys.
- The new scope/expiry/rate-limit fields are deliberately NOT surfaced in `SettingsApiKeysTab.tsx` (per this plan's `<frontend_scope>` — that UI work is deferred to Phase 65's ITAM console, which owns `services/apiService.ts`). The backend contract is additive so that phase can consume it without a migration.
- Full backend suite: 2066 passed / 35 skipped / 3 pre-existing unrelated failures (`test_agentic_ai` tool_choice kwarg, `test_e2e_integration` golden path, `test_rust_heartbeat_parity` agent_type field) — same baseline as 64-01/64-02, confirming no regressions from this plan.

---
*Phase: 64-user-management*
*Completed: 2026-08-12*

## Self-Check: PASSED

- FOUND: backend/api_key_auth.py
- FOUND: backend/api_key_endpoints.py
- FOUND: backend/auth_types.py
- FOUND: backend/rbac_service.py
- FOUND: backend/router_registry.py
- FOUND: backend/tests/test_api_key.py
- FOUND: backend/tests/test_api_key_auth.py
- FOUND: commit 75e7dc2e (Task 1)
- FOUND: commit ca6d5659 (Task 2)
- FOUND: commit b186ee3b (Task 3)
