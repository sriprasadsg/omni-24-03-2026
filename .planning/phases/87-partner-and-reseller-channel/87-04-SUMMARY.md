---
phase: 87-partner-and-reseller-channel
plan: 04
subsystem: auth
tags: [jwt, fastapi, mongodb, partner-suspension, fail-closed]

requires:
  - phase: 87-01
    provides: partner organizations (tenants type partner, partner.status) and rbac_defaults.is_partner_role
  - phase: 87-02
    provides: partner role fence and the tenant-type lookup in role assignment
provides:
  - backend/partner_status.py (SUSPENDED_MESSAGE, SUSPENDED_HEADERS, _raw_db, refuse_if_suspended)
  - per-request partner status check inside verify_token_async (every token issuer, MFA-pending routes included)
  - 403 + X-Partner-Suspended on login (after valid credentials) and refresh, audit reason partner_suspended
  - sync verify_token refuses partner roles
affects: [87-08, 87-10, 87-11]

actuals:
  tokens: 4400
  tasks: 2
  commits: 4
plan_head_before: b7d2d3d90b24d1a097d893272b4721d3eeea4e40
plan_head_after: 708951f6838e60be0f9cd078a90ec7f68dc38b94

tech-stack:
  added: []
  patterns:
    - "Suspension is a status read on the partner document at every request, not a login-only gate; the lookup fails closed (503) while the revocation check above it stays fail-open"
    - "Refusal messages for a suspended partner are only reachable after the password verified, so a wrong password keeps the generic 401"

key-files:
  created:
    - backend/partner_status.py
    - backend/tests/test_partner_suspension.py
  modified:
    - backend/authentication_service.py
    - backend/authentication_endpoints.py
    - backend/tests/test_session_revocation.py

key-decisions:
  - "The partner check sits after the tenant_id check and before the revocation check in verify_token_async, for partner roles only; non-partner roles make no lookup"
  - "Missing partner document, wrong tenant type or any status other than active all count as suspended (403); an unreadable status is 503, never a pass"
  - "Sync verify_token refuses every partner role with 401 because it cannot read the partner status and no partner route uses it"

patterns-established:
  - "partner_status._raw_db is the one monkeypatchable raw-handle provider for partner status tests"

requirements-completed: [PART-01]

coverage:
  - id: D1
    description: "A token issued before its partner was suspended gets 403 with X-Partner-Suspended and the stable message on its next request, including MFA-pending routes"
    requirement: PART-01
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_suspension.py#test_a_suspended_partner_token_is_refused_with_the_stable_message"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_suspension.py#test_a_suspended_partner_is_refused_even_where_mfa_pending_is_allowed"
        status: pass
    human_judgment: false
  - id: D2
    description: "Login with the right password for a suspended partner's user answers 403 with the message and audit reason partner_suspended; a wrong password answers 401 Invalid credentials"
    requirement: PART-01
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_suspension.py#test_login_with_the_right_password_for_a_suspended_partner_is_refused_and_audited"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_suspension.py#test_login_with_a_wrong_password_keeps_the_generic_refusal"
        status: pass
    human_judgment: false
  - id: D3
    description: "Refresh for a suspended partner's user answers 403 with the header; reinstating the partner restores sign-in"
    requirement: PART-01
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_suspension.py#test_refresh_for_a_suspended_partner_is_refused_with_the_header"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_suspension.py#test_reinstating_the_partner_restores_sign_in"
        status: pass
    human_judgment: false
  - id: D4
    description: "A failing status lookup answers 503 and never lets the request through; non-partner roles cause no lookup; sync verify_token refuses partner roles"
    requirement: PART-01
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_suspension.py#test_a_failing_status_lookup_answers_503_and_never_lets_the_request_through"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_suspension.py#test_a_non_partner_token_causes_no_partner_lookup"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_suspension.py#test_the_sync_verifier_refuses_every_partner_role"
        status: pass
    human_judgment: false

duration: 25 min
completed: 2026-11-02
status: complete
---

# Phase 87 Plan 04: Partner Suspension Enforcement Summary

**A suspended partner is locked out everywhere at once: one fail-closed status check in verify_token_async (so every token issuer is covered), plus clear 403 refusals at sign-in and refresh that only appear after a correct password.**

## Performance

- **Duration:** 25 min
- **Tasks:** 2 (both TDD)
- **Files:** 2 created, 3 modified

## Accomplishments

- `partner_status.refuse_if_suspended(role, tenant_id)`: no-op for non-partner roles; reads `tenants.partner.status` (type partner) from the raw handle; anything other than `active` (including no document) is 403 with `X-Partner-Suspended: 1` and the UI-SPEC message; an exception in the lookup is logged and answers 503 (fail closed).
- `verify_token_async` awaits it after the tenant_id check and before the revocation check, so access tokens issued by login, MFA, passkey, SSO or refresh before the suspension stop working on the next request, including routes allowing an MFA-pending session. The `except jwt.PyJWTError` does not swallow it.
- Sync `verify_token` refuses every partner role with the generic 401 (it cannot read the status and no partner route uses it).
- `login_for_access_token` checks after the credential and `account_is_active` checks (only valid credentials reach it) and audits `login.failure` with reason `partner_suspended`; `refresh_access_token` checks right after `account_is_active`.
- 14 tests in `test_partner_suspension.py`: 8 verifier tests on a real MongoDB database, 4 through the real auth router over the in-memory store.

## TDD Gate Compliance

- RED 1 `a29f13dd3`: 8 of 10 tests failed on the planned assertions (`DID NOT RAISE HTTPException`); the 2 that passed (active partner passes, non-partner makes no lookup) assert behaviors that already held. Semantic assessment: the target tests ran and failed because the verifier did not consult the partner status. Caveat: the standalone `partner_status.py` helper existed uncommitted in the working tree during the RED run (so the tests would import); it landed in the GREEN commit. The RED commit alone does not import.
- GREEN 1 `cd09603d9`: all 10 pass.
- RED 2 `3c4b6da34`: 3 of 4 endpoint tests failed (login returned 200 twice, refresh returned 401 instead of 403 because the unguarded refresh fell through to later token consumption that the in-memory store cannot serve); the wrong-password test passed as the unchanged behavior. The `gsd_run check tdd-red-evidence` classifier was not run (no report file produced); semantic inspection was done from the pytest output.
- GREEN 2 `708951f68`: all 14 pass. No refactor commit.

## Task Commits

1. Task 1 RED: `a29f13dd3` test(87-04)
2. Task 1 GREEN: `cd09603d9` feat(87-04)
3. Task 2 RED: `3c4b6da34` test(87-04)
4. Task 2 GREEN: `708951f68` feat(87-04)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Session revocation test mock lacked the tenant-type lookup from 87-02**
- **Found during:** Task 1 verification (the plan's verify command includes `test_session_revocation.py`)
- **Issue:** `test_user_update_revokes_sessions` and `test_user_update_without_session_impact_does_not_revoke` failed with `object MagicMock can't be used in 'await' expression`, because 87-02's `assert_role_fits_tenant_type` reads `db._db.tenants.find_one` and the mock database only set up `roles.find_one`. Unrelated to this plan's logic, but it blocked the plan's own verification.
- **Fix:** added `db._db.tenants.find_one = AsyncMock(return_value=None)` (unknown tenant passes through) to the test helper.
- **Files modified:** backend/tests/test_session_revocation.py
- **Commit:** `cd09603d9`

**Total deviations:** 1 auto-fixed (1 blocking). **Impact:** test mock only; no production code affected.

## Authentication Gates

None.

## Known Stubs

None.

## Threat Flags

None. The new refusal paths are the mitigations T-87-10 and T-87-11 from the plan; T-87-12 (lookup outage stops partner sessions only) is accepted as planned.

## Verification

- Task 1 command on private mongod 27998: 82 passed, 0 skipped (partner_suspension, session_revocation, admin_mfa_required).
- Task 2 command: 82 passed (partner_suspension, login_me_permissions, auth_mfa).
- Plan-level: `test_route_auth_baseline.py`, `test_auth_refresh_race.py`, `test_partner_roles.py`, `test_partner_tracer.py` together with the above: 162 passed, 0 skipped.
- Acceptance greps: `refuse_if_suspended` count 1 in authentication_service.py and 2 in authentication_endpoints.py (login line 201 after `account_is_active` at 194); 0 "fail-open" in partner_status.py; partner_status.py is 43 lines; authentication_endpoints.py gains exactly 8 lines.
- The private mongod was stopped before returning; the live mongod on 27017 was not touched and the backend was not restarted.

## Notes for Later Plans

- 87-08 (suspend route) must write `tenants.partner.status` to a value other than `active` and revoke sessions; the lookup treats every other value as suspended.
- The staged commits contain only this plan's hunks; the pre-existing user-side mfaExempt hunks in `authentication_service.py` and `authentication_endpoints.py` remain uncommitted in the working tree.

## Self-Check: PASSED

- backend/partner_status.py, backend/tests/test_partner_suspension.py: present on disk.
- Commits a29f13dd3, cd09603d9, 3c4b6da34, 708951f68 are ancestors of HEAD.
