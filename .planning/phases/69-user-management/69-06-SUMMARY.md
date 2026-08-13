---
phase: 69-user-management
plan: "06"
subsystem: auth
tags: [fastapi, mongodb, pyotp, bcrypt, fernet, mfa, totp, 2fa]

requires:
  - phase: 69-01
    provides: "User CRUD (db.users documents with email/role/tenantId), get_current_user session auth"
  - phase: 69-02
    provides: "rbac_service patterns, admin-gating conventions"
provides:
  - "backend/mfa_service.py: MongoDB TTL-backed mfa_sessions collection (expires_at, expireAfterSeconds=0) replacing the in-memory _mfa_sessions dict — survives restarts, works across workers"
  - "backend/mfa_service.py: encryption_service imported at module level (fail fast, no try/except swallow) — TOTP secrets always AES-256/Fernet-encrypted, no base64 plaintext-equivalent fallback; verify_encryption_service() health check"
  - "backend/mfa_service.py: disable_mfa(email, password) and regenerate_backup_codes(email, password) — password-confirmed, replacing the prior TOTP-confirmed disable"
  - "backend/mfa_service.py: backup codes bcrypt-hashed (auth_utils.hash_password/verify_password) instead of unsalted SHA-256"
  - "backend/mfa_endpoints.py: POST /api/mfa/backup-codes/regenerate (new route); POST /api/mfa/disable now takes {password}; POST /api/mfa/verify issues a JWT with mfa_verified=true"
  - "backend/authentication_endpoints.py: login flow awaits the now-async mfa_service.create_mfa_session()"
  - "components/UserProfilePage.tsx: disable-2FA form collects a password instead of a TOTP code, matching the tightened backend contract"
affects: [70-core-data-audit-customization]

tech-stack:
  added: []
  patterns:
    - "Lazy per-collection TTL-index creation with a module-level 'created' flag (mfa_service._mfa_index_created / _mfa_sessions_col()) — same pattern as sso_endpoints._sso_col() and saml_service._saml_raw_db(), now extended to a fourth short-lived MongoDB collection"
    - "Single-use session consumption via find_one_and_delete on the *first* verification attempt (success or failure) — mitigates MFA session-token brute forcing/replay; asymmetric with the backup-code path, which peeks (validate_mfa_session, non-destructive) so a wrong backup code doesn't burn the session"
    - "Bcrypt (auth_utils.hash_password/verify_password) for one-way-hashed single-use secrets that are only ever compared, never redisplayed — now applied to MFA backup codes in addition to passwords (auth_utils) and API keys (64-05's api_key_auth.py)"

key-files:
  created:
    - backend/tests/test_mfa.py
  modified:
    - backend/mfa_service.py
    - backend/mfa_endpoints.py
    - backend/authentication_endpoints.py
    - backend/tests/test_auth_mfa.py
    - components/UserProfilePage.tsx

key-decisions:
  - "Backup codes hashed with bcrypt instead of the plan's literal 'encrypted with encryption_service (AES-256)' instruction. One-way hashing is strictly safer for a value that is only ever compared, never redisplayed — reversible encryption would mean a leaked encryption key recovers every backup code ever issued, whereas a bcrypt hash cannot be reversed at all. This also fixes a real pre-existing weakness: the old code hashed codes with unsalted SHA-256 over an 8-digit (10^8) keyspace, which is GPU-crackable in seconds; bcrypt with a per-hash salt and cost factor closes that. Matches the codebase's existing convention (auth_utils.hash_password/verify_password, also used for passwords and 64-05's API keys)."
  - "verify_mfa_token() finds-and-deletes the MFA session on the very first attempt, whether or not the TOTP code turns out to be correct — literal reading of the plan's 'find_and_delete (single-use)' spec. A mistyped code forces the user to restart login and get a fresh session token; this trades UX friction for eliminating any window to brute-force guesses against one session token (rate-limited to 5/minute regardless, but this closes the gap entirely). The backup-code path (validate_mfa_session, non-destructive peek + explicit consume_mfa_session on success) intentionally keeps its prior forgiving behavior — a wrong backup-code guess doesn't burn the session, only the TOTP path was in scope for the Pitfall-1 rewrite."
  - "mfa_service functions use `email` as the account identifier throughout (disable_mfa(email, password), not disable_mfa(user_id, password) as the plan's prose describes) — matches every pre-existing function in the file (enroll_mfa, get_mfa_status, use_backup_code) and the fact that TokenData.username already carries the email value system-wide, per RESEARCH.md's Code Examples section."
  - "authentication_endpoints.py (not authentication_service.py, which the plan's frontmatter lists) is where the two-phase MFA login integration actually lives — the plan's Task 2 items 7/8 ('modify login to return mfa_session_token') were already implemented there prior to this plan. The only change needed was `await`ing the now-async create_mfa_session() call; authentication_service.py itself only holds JWT primitives (create_access_token, require_mfa dependency) and was not modified."

requirements-completed: [ITAM-USR-06]

coverage:
  - id: D1
    description: "MFA sessions persisted in a MongoDB TTL collection (mfa_sessions, expires_at/expireAfterSeconds=0) instead of an in-memory dict — survive restarts, work across workers (Pitfall 1)"
    requirement: "ITAM-USR-06"
    verification:
      - kind: unit
        ref: "backend/tests/test_mfa.py::TestMFASessionsTTL (13 tests: create/persist, TTL index creation, valid/expired/missing validation, naive-datetime handling, single-use verify_mfa_token, cleanup)"
        status: pass
    human_judgment: false
  - id: D2
    description: "TOTP secrets always AES-256(Fernet)-encrypted via encryption_service, imported at module level with no try/except fallback to base64; verify_encryption_service() health-check helper (Pitfall 2)"
    requirement: "ITAM-USR-06"
    verification:
      - kind: unit
        ref: "backend/tests/test_mfa.py::TestEncryption (5 tests: round-trip, non-base64-recoverable, health check pass/fail, no-silent-fallback)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Backup codes generated, bcrypt-hashed (not reversible/plaintext-equivalent), single-use, and usable for login recovery"
    requirement: "ITAM-USR-06"
    verification:
      - kind: unit
        ref: "backend/tests/test_mfa.py::TestBackupCodes (5 tests) + TestMFAEndpoints::test_verify_login_issues_jwt_with_mfa_verified_claim (backup-code login path already covered by pre-existing test_auth_mfa.py::test_verify_mfa_login_backup_code_success)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Disable 2FA and regenerate backup codes both require password confirmation (not TOTP), including UserProfilePage.tsx's form; endpoint rejects the old totp_code field"
    requirement: "ITAM-USR-06"
    verification:
      - kind: unit
        ref: "backend/tests/test_mfa.py::TestDisableMfa (4), TestRegenerateBackupCodes (2), TestMFAEndpoints::test_disable_endpoint_requires_password_field/test_disable_endpoint_success_with_password/test_disable_endpoint_wrong_password_returns_400/test_backup_codes_regenerate_endpoint"
        status: pass
      - kind: manual_procedural
        ref: "components/UserProfilePage.tsx disable-2FA form — password input renders and posts {password}; no live-browser click-through was run this session"
        status: unknown
    human_judgment: true
    rationale: "The React form change (password input replacing the 6-digit code field) is verified by code inspection and the backend contract test, but no live-browser UAT was run to confirm the rendered input type/label read correctly to an end user."
  - id: D5
    description: "Two-phase login flow (create_mfa_session -> verify_mfa_token -> JWT) preserved and the issued JWT now correctly carries mfa_verified=true so authentication_service.require_mfa() can be satisfied post-MFA"
    requirement: "ITAM-USR-06"
    verification:
      - kind: unit
        ref: "backend/tests/test_mfa.py::TestMFAEndpoints::test_verify_login_issues_jwt_with_mfa_verified_claim; backend/tests/test_auth_mfa.py::TestLoginEndpoint::test_login_mfa_required_returns_mfa_token + TestMFAVerifyLogin (6 tests, all still pass)"
        status: pass
    human_judgment: false

duration: ~55min
completed: 2026-08-13
status: complete
---

# Phase 69 Plan 06: 2FA/TOTP — fix MFA pitfalls, password-confirmed disable/regenerate Summary

**Replaced mfa_service.py's in-memory MFA session dict with a MongoDB TTL collection and its silent base64-encryption-fallback with a fail-fast encryption_service import; extended mfa_endpoints.py with password-confirmed disable/regenerate and a corrected mfa_verified JWT claim, while keeping every frontend-consumed route name frozen.**

## Performance

- **Duration:** ~55 min
- **Tasks:** 2
- **Files modified:** 6 (1 created, 5 modified)

## Accomplishments
- **Pitfall 1 fixed:** `mfa_service.py`'s `_mfa_sessions: dict` (in-memory, lost on restart) replaced with a `mfa_sessions` MongoDB collection using a TTL index (`expires_at`, `expireAfterSeconds=0`) — the exact lazy-index-creation pattern already established by `sso_endpoints._sso_col()` and `saml_service._saml_raw_db()` in this same codebase. `create_mfa_session`/`validate_mfa_session`/`consume_mfa_session`/`verify_mfa_token` are now all async and DB-backed; `verify_mfa_token` uses `find_one_and_delete` so a session token is single-use on the very first verification attempt, correct or not.
- **Pitfall 2 fixed:** `_encrypt_secret`/`_decrypt_secret` no longer `try/except ImportError` around `encryption_service` and fall back to base64 — `encryption_service` is imported at module level so a missing/broken encryption backend fails loudly at import time, not silently at write time. Added `verify_encryption_service()` — a callable round-trip health check (encrypt a probe string, decrypt it, assert equality) for future startup wiring.
- Backup codes switched from unsalted SHA-256 to bcrypt hashing (`auth_utils.hash_password`/`verify_password`) — fixes a real, exploitable weakness (an unsalted SHA-256 hash over an 8-digit/10^8-code keyspace is GPU-crackable in seconds) and matches the codebase's existing convention for one-way-hashed single-use secrets.
- `disable_mfa` and the new `regenerate_backup_codes` now require the account **password**, not a TOTP code — closing the gap where a stolen/lost authenticator alone could turn 2FA off. `disable_mfa` also revokes any pending MFA sessions for the account. `UserProfilePage.tsx`'s inline disable form updated in lockstep (password input, not a 6-digit code field) — this was a deliberate breaking tightening called out explicitly in the plan.
- New `POST /api/mfa/backup-codes/regenerate` endpoint (`{password}` -> new `backup_codes[]`) — backend-only, no frontend consumer yet per the plan's `<frontend_scope>` (deferred to the Phase 70 ITAM console).
- All five pre-existing frontend-consumed route names (`/setup`, `/verify-setup`, `/verify`, `/disable`, `/status`) are unchanged; verified by the plan's grep-based route gate against `MFASetupWizard.tsx`/`MFAVerifyModal.tsx`/`UserProfilePage.tsx` — all resolve, none dead.
- `get_mfa_status` now reports `has_backup_codes` and `last_used` in addition to the existing `enabled`/`enrolled_at`/`backup_codes_remaining` fields (additive; `UserProfilePage.tsx` already reads defensively).
- 40 new tests in `backend/tests/test_mfa.py` (encryption enforcement, TTL session lifecycle, enrollment, disable, regenerate, backup codes, status, and 6 endpoint-level tests including a regression guard on the `mfa_verified` JWT claim).

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix MFA pitfalls — persistent sessions and encryption enforcement** - `57a27292` (fix)
2. **Task 2: Extend MFA endpoints and integrate with authentication flow** - `4d0c728e` (feat)

**Plan metadata:** (this commit)

## Files Created/Modified
- `backend/mfa_service.py` — TTL-backed `mfa_sessions` collection, fail-fast encryption import + `verify_encryption_service()`, bcrypt backup codes, `disable_mfa`/`regenerate_backup_codes` (password-confirmed), extended `get_mfa_status`
- `backend/tests/test_mfa.py` — new file: 40 tests across encryption, backup codes, MFA session TTL lifecycle, enrollment, disable, regenerate, status, and endpoint-level behavior
- `backend/mfa_endpoints.py` — `/disable` now takes `{password}`; new `/backup-codes/regenerate`; `/verify` issues a JWT with `mfa_verified=true` and returns it in the response body
- `backend/authentication_endpoints.py` — `await`s `mfa_service.create_mfa_session(...)` (now async) in the login flow's MFA branch
- `backend/tests/test_auth_mfa.py` — 4 pre-existing mock `patch(...)` calls updated to `new_callable=AsyncMock` to match the now-async `mfa_service` functions they stub; all 21 pre-existing tests still pass
- `components/UserProfilePage.tsx` — disable-2FA inline form now collects a password (`type="password"` input) instead of a 6-digit TOTP code, and posts `{password}` to match the backend contract

## Decisions Made
- Bcrypt instead of literal "AES-256 encryption" for backup codes — see `key-decisions` in frontmatter for the full security rationale (one-way hashing is strictly safer for a compare-only, single-use secret than reversible encryption).
- `verify_mfa_token`'s single-use consumption happens on the first attempt regardless of code correctness (a wrong TOTP code still burns the session) — literal reading of the plan's `find_and_delete (single-use)` instruction and consistent with threat T-64-23's "single-use consumption" mitigation. The backup-code path intentionally keeps its prior forgiving (peek + explicit consume-on-success) behavior, since it wasn't part of the Pitfall-1 rewrite scope.
- Kept `email` (not `user_id`) as the identifier across all `mfa_service` functions, matching every pre-existing function signature in the file.
- `authentication_endpoints.py`, not `authentication_service.py` (which the plan's frontmatter lists under `files_modified`), is where the two-phase login integration actually lives and needed a one-line `await` fix — `authentication_service.py` itself was not touched.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `authentication_endpoints.py`'s login flow was not awaiting the now-async `create_mfa_session()`**
- **Found during:** Task 1, while making `create_mfa_session` async for the MongoDB TTL rewrite
- **Issue:** The login endpoint's MFA branch called `session_token = mfa_service.create_mfa_session(user["email"])` synchronously. Once `create_mfa_session` became `async` (required to insert into the new `mfa_sessions` collection), the un-awaited call would return a coroutine object instead of a token string, breaking every MFA-enabled login.
- **Fix:** Changed the call site to `session_token = await mfa_service.create_mfa_session(user["email"])`.
- **Files modified:** `backend/authentication_endpoints.py`
- **Verification:** `backend/tests/test_auth_mfa.py::TestLoginEndpoint::test_login_mfa_required_returns_mfa_token` passes.
- **Committed in:** `4d0c728e` (Task 2 commit — grouped with the other endpoint-level async-call-site fixes since it's the same class of change)

**2. [Rule 1 - Bug] 4 pre-existing `test_auth_mfa.py` mocks broke because they patched now-async `mfa_service` functions without `new_callable=AsyncMock`**
- **Found during:** Task 1/2, caught by a full-file regression run (not the plan's own targeted `<verify>` commands)
- **Issue:** `patch("mfa_service.create_mfa_session", return_value=...)`, two `patch("mfa_service.validate_mfa_session", return_value=...)` calls, and `patch("mfa_service.consume_mfa_session")` all used plain (sync) `MagicMock` patches. Once those three functions became `async def` (required for the MongoDB TTL rewrite) and their call sites started `await`ing them, the un-updated mocks would make `await <MagicMock() or str>` raise `TypeError: object ... can't be used in 'await' expression`.
- **Fix:** Added `new_callable=AsyncMock` to all 4 patch calls.
- **Files modified:** `backend/tests/test_auth_mfa.py`
- **Verification:** `pytest backend/tests/test_auth_mfa.py -q` — 21/21 pass, both standalone and combined with `test_mfa.py` in either collection order.
- **Committed in:** `4d0c728e` (Task 2 commit)

**3. [Rule 1 - Bug] `mfa_endpoints.py`'s `/api/mfa/verify` route shares a rate-limit bucket with `test_auth_mfa.py`'s own 5 calls to the same route, causing a 429 once `test_mfa.py`'s endpoint tests were added to the same pytest process**
- **Found during:** Task 2, caught by a combined-file regression run
- **Issue:** `mfa_endpoints.py`'s `@limiter.limit("5/minute")` decorator binds to the single process-wide `rate_limiter.limiter` singleton at import time — not the per-test `Limiter()` instance each test file constructs for its `FastAPI.state.limiter`. `test_auth_mfa.py` already makes 5 calls to `/api/mfa/verify` across its test methods (exactly at the limit); adding `test_mfa.py`'s own `/verify` call to the same pytest process pushed the shared bucket to 6, 429-ing whichever test ran 6th regardless of which file it was in.
- **Fix:** Added an autouse `_reset_shared_rate_limiter` fixture to `test_mfa.py` that resets `rate_limiter.limiter._storage` before and after every test — the same isolation pattern already established by `test_ldap_service.py::_reset_ldap_rate_limit`.
- **Files modified:** `backend/tests/test_mfa.py`
- **Verification:** `pytest backend/tests/test_auth_mfa.py backend/tests/test_mfa.py -q` and the reverse file order both pass 61/61; full backend suite unaffected.
- **Committed in:** `4d0c728e` (Task 2 commit)

---

**Total deviations:** 3 auto-fixed (1 Rule 3 — blocking call-site fix required by this plan's own async rewrite, 2 Rule 1 — pre-existing test isolation gaps this plan's changes exposed, caught and fixed before commit via full-suite regression runs)
**Impact on plan:** All three fixes were necessary for the plan's must-haves to hold for real traffic and for the existing test suite to stay green in every collection order. No architectural changes; no scope creep beyond making this task's own new/changed code work correctly against the rest of the codebase.

## Issues Encountered
None beyond the deviations documented above.

## User Setup Required
None - no external service configuration required. `encryption_service`'s `PAYMENT_ENCRYPTION_KEY` env var (shared across payment/ldap/saml/mfa) already governs production-hardness of the AES-256 encryption used here — if unset outside dev/test, `encryption_service.py` itself refuses to start (pre-existing behavior, unchanged by this plan). `verify_encryption_service()` is provided as a callable health check but is not wired into app startup in this plan (out of the plan's stated `files_modified` scope); a future phase could call it from a startup hook or ops health endpoint.

## Next Phase Readiness
- ITAM-USR-06 (2FA) is now fully implemented: MongoDB-persistent MFA sessions, enforced encryption with a health-check helper, bcrypt-hashed backup codes, password-confirmed disable/regenerate, and a correct `mfa_verified` JWT claim for downstream `require_mfa`-gated endpoints.
- The new `POST /api/mfa/backup-codes/regenerate` route has no frontend consumer yet — deferred to Phase 70's ITAM console work per this plan's `<frontend_scope>`, which owns the frontend service layer additions going forward.
- Full backend suite: 2106 passed / 35 skipped / 3 pre-existing unrelated failures (`test_agentic_ai` tool_choice kwarg, `test_e2e_integration` golden path, `test_rust_heartbeat_parity` agent_type field) — identical baseline to 64-05, confirming no regressions from this plan.
- `verify_mfa_token`'s single-use-on-first-attempt semantics (session dies even on a wrong TOTP code) is a UX/security tradeoff worth surfacing to product before a UAT pass: a user who mistypes their code must restart login from `/api/auth/login` rather than getting a second try against the same session.

---
*Phase: 64-user-management*
*Completed: 2026-08-13*

## Self-Check: PASSED

- FOUND: backend/mfa_service.py
- FOUND: backend/mfa_endpoints.py
- FOUND: backend/authentication_endpoints.py
- FOUND: backend/tests/test_auth_mfa.py
- FOUND: backend/tests/test_mfa.py
- FOUND: components/UserProfilePage.tsx
- FOUND: commit 57a27292 (Task 1)
- FOUND: commit 4d0c728e (Task 2)
