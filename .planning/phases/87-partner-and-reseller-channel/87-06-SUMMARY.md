---
phase: 87-partner-and-reseller-channel
plan: 06
subsystem: api
tags: [fastapi, mongodb, invites, password-set, rate-limiting, multi-tenant]

requires:
  - phase: 87-01
    provides: PartnerError, partner roles, partner_pool raw-handle helper
  - phase: 87-15
    provides: partner stored shape this module invites into
provides:
  - partner_invites module (invite, issue_invite, resend, invite_state, member_status, email_in_use, send_invite_email, normalize_email)
  - public POST /api/auth/invite/status (token in the body, 10/minute)
  - invites collection (SHA-256 of the link secret only) and the password_reset_tokens.invite flag
affects: [87-08, 87-09, 87-10]

actuals:
  tokens: 7000
  tasks: 2
  commits: 4
plan_head_before: 0caaec636ec2e660c557c143141225d4bb6d7d62
plan_head_after: 52dccb40568e1bb51ba1baa308ec2e4f115a9f20

tech-stack:
  added: []
  patterns:
    - "Invite link lives in password_reset_tokens with an ISO expires_at and NO creation-time field (its 1 h TTL index keys on that field), so the existing confirm route sets the password and consumes it"
    - "invites keeps only the SHA-256 of the secret; used = token row gone, superseded = supersededAt set"
    - "Async route tests use httpx.ASGITransport so motor stays on the pytest loop (TestClient would cross loops)"

key-files:
  created:
    - backend/partner_invites.py
    - backend/invite_endpoints.py
    - backend/tests/test_partner_invites.py
  modified:
    - backend/router_registry.py
    - backend/tests/test_route_auth_baseline.py

key-decisions:
  - "Invite state is derived, not stored: invalid = no invites record or supersededAt, used = record without a token row, expired = past expires_at, else valid"
  - "resend() treats a person with no invite-flagged token row (consumed, or never invited) as active and refuses, so a partner can never reset a signed-in person's password or an existing admin's"
  - "Log lines in partner_invites carry only the tenant id and exception class name, never the address, token or link"

patterns-established:
  - "PartnerError 409 email_unavailable with one fixed message for every clash, case-insensitive, across all organizations"

requirements-completed: [PART-02, PART-01]

coverage:
  - id: D1
    description: "invite() stores an Active user with an unknown password hash, a 7-day token row with invite true and no creation-time field, and a hash-only invites record"
    requirement: PART-02
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_invites.py#test_invite_stores_an_active_user_with_a_password_nobody_knows"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_invites.py#test_invite_stores_a_seven_day_token_row_without_a_creation_time_and_a_hash_only_record"
        status: pass
    human_judgment: false
  - id: D2
    description: "invite() returns only {user: {id, name, email, role}, emailSent}; no token, link or password"
    requirement: PART-02
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_invites.py#test_invite_returns_no_token_no_link_and_no_password"
        status: pass
    human_judgment: false
  - id: D3
    description: "An address in use anywhere (any case) is refused 409 email_unavailable with the generic message and nothing is stored"
    requirement: PART-02
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_invites.py#test_an_address_in_use_anywhere_is_refused_generically_and_nothing_is_stored"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_invites.py#test_an_address_held_by_a_user_with_mixed_case_is_refused"
        status: pass
    human_judgment: false
  - id: D4
    description: "The existing reset-password/confirm route accepts the invite token once, then the status is used; valid/expired/invalid/used all classified"
    requirement: PART-02
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_invites.py#test_status_is_valid_then_used_after_the_existing_confirm_route_sets_a_password"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_invites.py#test_status_is_expired_invalid_and_never_echoes_the_token"
        status: pass
    human_judgment: false
  - id: D5
    description: "resend() supersedes the old link and issues a new one; refused 409 already_active after a password is set or for a never-invited user"
    requirement: PART-01
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_invites.py#test_resend_supersedes_the_old_link_and_issues_a_new_seven_day_one"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_invites.py#test_resend_is_refused_once_the_person_has_set_a_password"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_invites.py#test_resend_is_refused_for_a_user_who_was_never_invited"
        status: pass
    human_judgment: false
  - id: D6
    description: "send_invite_email sends nothing without an http(s) FRONTEND_URL or a mail configuration; with both, the link goes only to the invitee; no log line holds the token or link"
    requirement: PART-02
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_invites.py#test_without_a_link_base_nothing_is_sent_and_nothing_secret_is_logged"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_invites.py#test_with_mail_configured_the_link_goes_only_to_the_invitee_and_never_to_a_log"
        status: pass
    human_judgment: false
  - id: D7
    description: "POST /api/auth/invite/status is public, body-only, limited to 10 a minute, mounted, and the only new reviewed-unauthenticated entry"
    requirement: PART-02
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_invites.py#test_status_route_is_limited_to_ten_a_minute"
        status: pass
      - kind: integration
        ref: "backend/tests/test_route_auth_baseline.py (route walk over the mounted app)"
        status: pass
    human_judgment: false
  - id: D8
    description: "Real email delivery and the accept-invite page"
    requirement: PART-02
    human_judgment: true
    rationale: "SMTP is not configured on this VM and FRONTEND_URL is unverified (A-87-A10), so every invite here returns emailSent false; delivery is exercised only against a mocked sender"

duration: 22 min
completed: 2026-11-02
status: complete
---

# Phase 87 Plan 06: Invite Flow Summary

**Seven-day single-use invite links through the existing password-set route: `partner_invites` creates the person with an unknown password hash, stores only the link secret's SHA-256, emails the link (never returns or logs it), and a public rate-limited `POST /api/auth/invite/status` tells valid, expired, used or invalid apart without the token reaching any URL.**

## Performance

- **Duration:** about 22 min
- **Tasks:** 2 (both TDD)
- **Files:** 3 created, 2 modified

## Accomplishments

- `partner_invites.py` (205 lines): `invite` stores an Active user (lowercased email, bcrypt hash of 48 random bytes nobody sees), a `password_reset_tokens` row `{token, email, expires_at +7d ISO, invite: true}` with no creation-time field, and an `invites` record holding only `tokenHash`. It returns `{user: {id, name, email, role}, emailSent}` and nothing else.
- One generic refusal for every address clash (409 `email_unavailable`, case-insensitive, any organization), checked before anything is written; a `DuplicateKeyError` race maps to the same refusal.
- The existing `POST /api/auth/reset-password/confirm` accepts the invite token unchanged (that file was not edited) and consumes the row; status then reads `used`.
- `resend` supersedes the old link (`supersededAt`, token rows deleted so the old link reads `invalid`) and issues a new one; it refuses with 409 `already_active` once a password is set and also for anyone who was never invited, so a partner cannot reset a signed-in person (PROH-87-02).
- `invite_endpoints.py`: public `POST /api/auth/invite/status`, `10/minute`, token in the body (1..512 chars, 422 otherwise); mounted after `auth_password_reset_endpoints` and listed once in `REVIEWED_UNAUTHENTICATED`.

## TDD Gate Compliance

| Task | RED | GREEN |
|------|-----|-------|
| 1 | `c54d2b877` test(87-06): 17 tests run against a `NotImplementedError` stub and all 17 fail at the target call | `feefc833d` feat(87-06): 17 pass |
| 2 | `a92458fd7` test(87-06): 5 new tests against an empty-router stub fail on 404 / zero routes (assertion failures for the planned behavior) | `52dccb405` feat(87-06): 22 pass |

Semantic assessment: both RED runs executed the named tests and failed on the planned behavior, not on import, syntax or fixture faults. Task 1's RED failures are `NotImplementedError` from the stub rather than assertion text; they could not pass without the implementation. `gsd_run check tdd-red-evidence` was not run (the plan is `type: execute`, not `type: tdd`). No refactor commits.

## Task Commits

1. Task 1 RED: `c54d2b877`, GREEN: `feefc833d`
2. Task 2 RED: `a92458fd7`, GREEN: `52dccb405`

## Verification

- `test_partner_invites.py`: 22 passed, 0 skipped (private mongod on 27998, stopped afterwards).
- `test_partner_invites.py test_route_auth_baseline.py test_catalogue_manifest.py`: 56 passed, 1 failed, the known baseline `test_sidebar_and_app_agree_with_manifest`.
- `test_catalogue_route_parity.py test_partner_route_walk.py test_catalogue_slice_partners.py test_partner_tracer.py`: 78 passed, 1 failed, the known baseline `test_ledger_ratchets` (no invite entry in its output).
- Acceptance: `grep -c created_at partner_invites.py` 0; `grep -cE "logger\.[a-z]+\(.*token"` 0; `grep -c localhost` 0; 205 lines; baseline entry count 1; `invite_endpoints` in router_registry 1; `Query(` in invite_endpoints 0.

## Deviations from Plan

None - plan executed exactly as written. Two notes that are not deviations:

- Tests add `_app_log(caplog)`, which excludes the MongoDB driver's own debug command trace from the "nothing secret is logged" assertions (the driver logs the filters the tests themselves issue); the check still covers every logger of this codebase.
- `test_route_auth_baseline.py` and `router_registry.py` carry user-side file-mode flips in the working tree; only the content hunks were committed (the baseline file as a mode-100644 blob). `auth_password_reset_endpoints.py` was not touched.

## Authentication Gates

None.

## Known Stubs

None. (The two RED-commit stubs were replaced in their GREEN commits.)

## Issues Encountered

None.

## Threat Surface

No surface beyond the plan's register: T-87-16 (token never returned or logged), T-87-17 (256-bit token, SHA-256 at rest, 10/minute, single use), T-87-18 (one generic clash message), T-87-19 (token in body, no logger call carries it) are all mitigated and tested. The new public route is the one the plan names. Open assumption A-87-A10: `FRONTEND_URL` is unverified on this VM and SMTP is unconfigured, so invites here return `emailSent: false`; the Super Admin sets a password in User Management instead.

## Next Phase Readiness

Ready for 87-08 (appoint a partner) and 87-09 (customer creation and colleague invites), which call `partner_invites.invite` and `resend`, and for the accept-invite page that posts to `/api/auth/invite/status` then `/api/auth/reset-password/confirm`. Callers must authorize who may invite/resend; this module only enforces the takeover rules.

## Self-Check: PASSED

- FOUND: backend/partner_invites.py, backend/invite_endpoints.py, backend/tests/test_partner_invites.py
- FOUND commits: c54d2b877, feefc833d, a92458fd7, 52dccb405 (all ancestors of HEAD)
