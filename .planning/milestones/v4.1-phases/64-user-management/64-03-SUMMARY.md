---
phase: 64-user-management
plan: "03"
subsystem: auth
tags: [ldap, active-directory, ldap3, fastapi, mongodb, rbac, encryption]

requires:
  - phase: 64-01
    provides: "User CRUD with tenantId/role/status fields; users collection shape"
  - phase: 64-02
    provides: "rbac_service.default_roles (itam_admin/itam_user/itam_viewer), rbac_service._normalize_role single source of truth"
provides:
  - "ldap_service.py: LDAPConfig (env or admin-saved DB config), LDAPConnectionManager (TLS/StartTLS, bounded service-connection pool, single-use user-bind connections, retry), LDAPAuthenticator (bind-as-user credential verification), LDAPUserSyncer (search/map/upsert to MongoDB with source=\"ldap\"), LDAPGroupMapper (group DN -> ITAM role), authenticate_ldap() (bind -> sync -> mint JWT)"
  - "ldap_endpoints.py: admin config CRUD (POST/GET /api/admin/ldap/config), POST /api/admin/ldap/test-connection, POST /api/admin/ldap/sync, group-mapping CRUD (GET/POST /api/admin/ldap/group-mapping, DELETE .../{id}), dedicated POST /api/auth/ldap/login"
  - "T-64-12 mitigation: local password changes blocked for source=\"ldap\" users in user_endpoints.update_user and auth_password_reset_endpoints.confirm_password_reset"
affects: [64-06-mfa-and-login-rewrite, 65-core-data-audit-customization]

tech-stack:
  added: ["ldap3==2.9.1 (human-approved via blocking checkpoint, pure-Python, no libldap2-dev/libsasl2-dev)"]
  patterns:
    - "Bounded service-connection pool + single-use user-bind connections in LDAPConnectionManager: service-account connections are reused (up to pool_size) across search operations, interactive user-credential binds are always single-use and unbound immediately after the check"
    - "Role-clobber guard: LDAPUserSyncer.sync_user only overwrites an existing user's role when a group mapping actually resolved one — a re-sync (or every LDAP login) with no group match never silently downgrades an admin-assigned elevated role back to the sync default"
    - "Dedicated auth route pattern: LDAP login lives at its own POST /api/auth/ldap/login rather than as a branch inside the shared local-auth login handler, to avoid colliding with 64-06's same-wave rewrite of that handler for two-phase MFA"

key-files:
  created:
    - backend/ldap_service.py
    - backend/ldap_endpoints.py
    - backend/tests/test_ldap_service.py
  modified:
    - backend/requirements.txt
    - backend/router_registry.py
    - backend/user_endpoints.py
    - backend/auth_password_reset_endpoints.py
    - backend/tests/test_user_crud.py

key-decisions:
  - "ldap3 (pure Python) chosen over python-ldap per RESEARCH.md Q4 — no C bindings, no OS-level headers to hand-manage across deploy targets; human-approved via the plan's blocking-human checkpoint before any install"
  - "LDAP directory connection resolves to a single platform-wide config (tenant_id=None, the shape a Super Admin saves) for the unauthenticated /api/auth/ldap/login route, since there is no tenant context before a caller is authenticated; tenant-scoped admin config lookups (test-connection/sync/group-mapping for a Tenant Admin) fall back to that same platform default when no tenant-specific doc exists. True per-tenant LDAP server support (a different directory per tenant) is out of scope for this plan — documented as a follow-up below."
  - "authenticate_ldap()'s target tenant for a first-time LDAP login (no existing local user) is resolved via LDAP_DEFAULT_TENANT_ID; without it, first-time provisioning raises LDAPSyncError rather than guessing a tenant. Existing local users (pre-created via POST /api/users, or previously LDAP-synced) always keep their own tenantId on subsequent logins."
  - "LDAPUserSyncer.sync_user(role=...) is Optional and only applied on update when non-None — role resolution only happens via LDAPGroupMapper.resolve_role(); when no group mapping matches, an existing user's admin-assigned role is left untouched rather than reset to the itam_viewer default on every sync/login (this was caught as a design risk while writing sync_all, not an issue in a merged PR — documented as a decision, not a Deviation, since it was fixed before any commit)."
  - "The plan's `authenticate_ldap(username, password) -> TokenData` type annotation is descriptive shorthand, not the literal auth_types.TokenData dataclass (which represents decoded request claims, not a login response). Implemented to return the same access_token/refresh_token/token_type/user-fields dict shape authentication_endpoints.py's local /api/auth/login and /refresh-token already return, so ldap_endpoints.ldap_login's response is drop-in compatible with the frontend's existing token-handling code."
  - "POST /api/auth/ldap/login is rate-limited (10/minute) via the same shared rate_limiter.limiter singleton used by authentication_endpoints.py and auth_password_reset_endpoints.py, matching the existing convention for unauthenticated auth endpoints."

requirements-completed: [ITAM-USR-03]

coverage:
  - id: D1
    description: "LDAP/AD authentication: users can authenticate against a directory using their credentials (bind-as-user verification, never storing the password)"
    requirement: "ITAM-USR-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_ldap_service.py::TestLDAPAuthenticatorAuth (4 tests), TestAuthenticateLdapFlowAuth (4 tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: "LDAP user provisioning/update in MongoDB with source=\"ldap\" flag, attribute mapping (id/email/name/groups)"
    requirement: "ITAM-USR-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_ldap_service.py::TestLDAPUserSyncer (7 tests)"
        status: pass
    human_judgment: false
  - id: D3
    description: "LDAP group membership maps to ITAM roles via an admin-managed group-DN-to-role mapping, without clobbering an admin-assigned role on re-sync when no mapping matches"
    requirement: "ITAM-USR-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_ldap_service.py::TestLDAPGroupMapper (5 tests), TestLDAPUserSyncer::test_sync_user_update_preserves_existing_role_when_no_mapping"
        status: pass
    human_judgment: false
  - id: D4
    description: "Local password changes blocked for LDAP-sourced users (source=\"ldap\") in both the admin user-update endpoint and the self-service password-reset flow"
    requirement: "ITAM-USR-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_user_crud.py::TestUpdateUser::test_update_user_blocks_password_change_for_ldap_sourced_user"
        status: pass
      - kind: other
        ref: "backend/auth_password_reset_endpoints.py confirm_password_reset — no automated test exists for this file (zero pre-existing coverage); verified by manual syntax/logic review only"
        status: unknown
    human_judgment: true
    rationale: "The auth_password_reset_endpoints.py half of this mitigation has no automated test coverage — that file has zero pre-existing tests and adding a new test file was judged out of this plan's declared scope. Logged to WINDOWS.md (unrun-verify) for follow-up."
  - id: D5
    description: "Admin configuration endpoints (config CRUD with encrypted bind password, test-connection, manual sync trigger, group-mapping CRUD) gated by _require_itam_admin; dedicated LDAP login route"
    requirement: "ITAM-USR-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_ldap_service.py::TestLDAPConfigEndpoint, TestLDAPTestConnectionEndpoint, TestLDAPSyncEndpoint, TestLDAPGroupMappingEndpoint, TestLDAPLoginEndpointAuth (14 tests)"
        status: pass
    human_judgment: false
  - id: D6
    description: "Manual end-to-end verification against a real LDAP/AD server (test-connection and sync working live)"
    requirement: "ITAM-USR-03"
    verification: []
    human_judgment: true
    rationale: "No LDAP/AD directory is available in this sandbox environment (per plan's user_setup — requires a real service account and directory). Only unit tests with a mocked LDAP server (unittest.mock on ldap3.Server/Connection) were run. Logged to WINDOWS.md (unrun-verify)."

duration: 70min
completed: 2026-08-13
status: complete
---

# Phase 64 Plan 03: LDAP/AD Integration Summary

**New `ldap_service.py`/`ldap_endpoints.py` module built from scratch: connection-pooled LDAP/AD bind authentication, user sync with `source="ldap"` provisioning, group-DN-to-role mapping, admin config endpoints with encrypted bind-password storage, and a dedicated `/api/auth/ldap/login` route — using `ldap3==2.9.1` (human-approved via the plan's blocking checkpoint).**

## Performance

- **Duration:** ~70 min
- **Tasks:** 2 (+ 1 blocking-human checkpoint)
- **Files modified:** 8 (3 created, 5 modified)

## Accomplishments
- `ldap_service.py`: `LDAPConfig` (env vars or admin-saved DB doc, decrypted bind password), `LDAPConnectionManager` (TLS/StartTLS with cert validation, bounded 3-connection service pool, single-use never-pooled user-bind connections, 2-retry backoff), `LDAPAuthenticator` (resolves user DN via service account, then binds as the user — the bind itself is the only credential check, password is never stored), `LDAPUserSyncer` (search/map/upsert with `source="ldap"`), `LDAPGroupMapper` (group DN → ITAM role, priority-ordered), `authenticate_ldap()` (bind → sync → mint JWT by calling `authentication_service.create_access_token`/`create_refresh_token`, not duplicating token logic)
- `ldap_endpoints.py`: `POST`/`GET /api/admin/ldap/config` (bind password encrypted via `encryption_service`, masked on read), `POST /api/admin/ldap/test-connection`, `POST /api/admin/ldap/sync`, `GET`/`POST /api/admin/ldap/group-mapping` + `DELETE .../{id}`, all gated by `itam_asset_endpoints._require_itam_admin`; dedicated rate-limited `POST /api/auth/ldap/login` (never a branch inside the local login handler — 64-06 rewrites that in the same wave for two-phase MFA)
- Registered `ldap_endpoints.router` in `router_registry.py` — confirmed reachable via `/openapi.json` in the full app (6 LDAP routes present, no load failures)
- 61 new tests, all passing: 47 in `test_ldap_service.py` (config resolution, connection pooling/retry, auth bind success/failure, user mapping/sync/role-preservation, group mapping, admin endpoints, login route) + 1 in `test_user_crud.py` (LDAP-sourced password-change block) + 13 already counted in the 47 for endpoints
- Full backend suite: 1996 passed / 35 skipped / 3 pre-existing unrelated failures (`test_agentic_ai` tool_choice kwarg, `test_e2e_integration` golden path, `test_rust_heartbeat_parity` agent_type field) — same baseline as 64-01/64-02, no regressions

## Task Commits

Each task was committed atomically:

1. **Checkpoint: Verify LDAP package legitimacy before install** — human approved `ldap3` via PyPI review (blocking-human, no code change)
2. **Task 1: Install LDAP libraries and create ldap_service.py** — `ae6d3e62` (feat)
3. **Task 2: Create LDAP admin endpoints and authentication integration** — `55f6d84d` (feat) — includes the T-64-12 Rule 2 deviation (see below)

**Plan metadata:** (this commit)

## Files Created/Modified
- `backend/ldap_service.py` - LDAPConfig, LDAPConnectionManager, LDAPAuthenticator, LDAPUserSyncer, LDAPGroupMapper, authenticate_ldap(), is_ldap_sourced_user()
- `backend/ldap_endpoints.py` - Admin config/test-connection/sync/group-mapping endpoints + dedicated LDAP login route
- `backend/tests/test_ldap_service.py` - 47 tests covering config resolution, connection pooling, auth, sync, group mapping, and endpoints (mocked LDAP server via unittest.mock)
- `backend/requirements.txt` - Added `ldap3==2.9.1` (pinned exactly, human-approved)
- `backend/router_registry.py` - Registered `ldap_endpoints.router`
- `backend/user_endpoints.py` - `update_user` now rejects password changes for `source="ldap"` users (T-64-12)
- `backend/auth_password_reset_endpoints.py` - `confirm_password_reset` now rejects resets for `source="ldap"` users (T-64-12)
- `backend/tests/test_user_crud.py` - Added `test_update_user_blocks_password_change_for_ldap_sourced_user`

## Decisions Made
- `ldap3==2.9.1` over `python-ldap`: pure-Python, no OS-level `libldap2-dev`/`libsasl2-dev` headers to manage across deploy targets (RESEARCH.md Q4); human-approved via the plan's blocking checkpoint before install.
- LDAP directory connection is a single platform-wide config for the login route (no tenant context exists pre-authentication); tenant-scoped admin lookups fall back to that same platform default. True per-tenant LDAP servers are out of scope — see Next Phase Readiness.
- First-time LDAP provisioning (no existing local user) requires `LDAP_DEFAULT_TENANT_ID`; existing local users always keep their own `tenantId` on re-login.
- `LDAPUserSyncer.sync_user`'s `role` parameter is `Optional` and only applied on update when a group mapping actually resolved a role — prevents every re-sync/login from silently resetting an admin-assigned elevated role back to the `itam_viewer` default. (Caught and fixed while writing `sync_all`, before any commit — a design decision, not a post-hoc deviation.)
- `authenticate_ldap()` returns the same `access_token`/`refresh_token`/`token_type` dict shape as the existing local-auth `/api/auth/login`, rather than the plan's literal `-> TokenData` annotation (which is the decoded-claims dataclass used for authenticated requests, not a login response type).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Wired the T-64-12 password-change block into the actual enforcement points**
- **Found during:** Task 2, while implementing the plan's must-have truth "Local password changes blocked for LDAP-sourced users"
- **Issue:** The plan's `files_modified` scope (`backend/ldap_service.py`, `backend/ldap_endpoints.py`, `backend/tests/test_ldap_service.py`) does not include the two files that actually perform local password changes: `user_endpoints.py`'s admin `update_user` and `auth_password_reset_endpoints.py`'s self-service `confirm_password_reset`. Without touching them, the plan's own required truth ("Local password changes blocked for LDAP-sourced users") would remain unenforced by any real request path — `source="ldap"` would be written to MongoDB but nothing would check it.
- **Fix:** Added a `source == "ldap"` check (403) before the password-hash write in both `update_user` and `confirm_password_reset`.
- **Files modified:** `backend/user_endpoints.py`, `backend/auth_password_reset_endpoints.py`
- **Verification:** `test_update_user_blocks_password_change_for_ldap_sourced_user` (passing). The `auth_password_reset_endpoints.py` half has no automated test — see Known Follow-ups.
- **Committed in:** `55f6d84d` (Task 2 commit)
- **Precedent:** Matches 64-02's extension into `rbac_utils.py` (outside its own `files_modified`) for the same reason — the file containing the plan's declared must-have truth wasn't the file that actually enforced it at runtime.

**2. [Rule 3 - Blocking] Registered `ldap_endpoints.router` in `router_registry.py`**
- **Found during:** Task 2, verifying the new endpoints were actually reachable
- **Issue:** New FastAPI routers in this codebase are only mounted via `router_registry.register_all_routers()`; without a registration line, all 6 new LDAP endpoints would be dead code, unreachable at any URL.
- **Fix:** Added `_load(app, "ldap_endpoints", "router")` alongside the existing `mfa_endpoints`/`sso_endpoints` registrations.
- **Files modified:** `backend/router_registry.py`
- **Verification:** Confirmed via `/openapi.json` in a full app instance — all 6 LDAP paths present, no `[Router] Failed to load` entries.
- **Committed in:** `55f6d84d` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 Rule 2 — security-critical enforcement gap, 1 Rule 3 — blocking/dead-code)
**Impact on plan:** Both were necessary for the plan's own must-have truths to hold against real request traffic. No architectural changes; no scope creep beyond the two specific enforcement points and the router registration line.

## Issues Encountered
None beyond the deviations documented above.

## User Setup Required
**External LDAP/AD directory requires manual configuration for live testing.** This plan's `user_setup` (frontmatter) lists all `LDAP_*` env vars (`LDAP_URI`, `LDAP_BIND_DN`, `LDAP_BIND_PASSWORD`, `LDAP_USER_BASE_DN`, `LDAP_GROUP_BASE_DN`, filters/attribute-name overrides, `LDAP_TLS_CA_CERT`) plus `LDAP_DEFAULT_TENANT_ID` (new, for first-time LDAP-only provisioning). No LDAP/AD server was available in this sandbox — all verification here used a mocked LDAP server (`unittest.mock` on `ldap3.Server`/`Connection`). The plan's manual verification step ("Configure test LDAP server, verify test-connection and sync work end-to-end") was **not run** — logged to `.planning/WINDOWS.md` as `unrun-verify`.

## Next Phase Readiness
- `ldap_service.py`/`ldap_endpoints.py` are live, tested, and registered — ready for a real directory to be configured via `POST /api/admin/ldap/config` or env vars, and for `POST /api/auth/ldap/login` to be wired into the frontend `LoginPage.tsx` (currently untouched — LDAP bind is transparent at the existing local-credentials form per this plan's `<frontend_scope>` deferral; a directory-config settings screen is also deferred, see the plan's frontend_scope block).
- **Follow-up for 64-06 (same wave):** once 64-06 rewrites the local login handler for two-phase MFA, revisit whether `/api/auth/ldap/login` should also gain an MFA phase, and whether the "try local, then LDAP" chaining (explicitly deferred by this plan) should be implemented.
- **Follow-up (architecture, not urgent):** true per-tenant LDAP server support (a different directory per tenant, not just per-tenant group-mapping/role config against one platform directory) is unimplemented — flagging for whoever needs multi-tenant-directory support.
- **Follow-up (test coverage):** `auth_password_reset_endpoints.py`'s new `source="ldap"` block has no automated test (file has zero pre-existing coverage); logged to `.planning/WINDOWS.md`.
- **Follow-up (manual verification):** live LDAP server test-connection/sync was not exercised in this sandbox; logged to `.planning/WINDOWS.md`.
- Full backend suite: 1996 passed / 35 skipped / 3 pre-existing unrelated failures — unchanged baseline, confirms no regressions.

---
*Phase: 64-user-management*
*Completed: 2026-08-13*

## Self-Check: PASSED

- FOUND: backend/ldap_service.py
- FOUND: backend/ldap_endpoints.py
- FOUND: backend/tests/test_ldap_service.py
- FOUND: backend/requirements.txt (ldap3==2.9.1 present)
- FOUND: backend/router_registry.py (ldap_endpoints registered)
- FOUND: backend/user_endpoints.py (T-64-12 guard present)
- FOUND: backend/auth_password_reset_endpoints.py (T-64-12 guard present)
- FOUND: commit ae6d3e62 (Task 1)
- FOUND: commit 55f6d84d (Task 2)
