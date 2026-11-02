---
phase: 87-partner-and-reseller-channel
plan: 08
subsystem: api
tags: [fastapi, mongodb, partner-channel, audit, session-revocation, seat-pool]

requires:
  - phase: 87-01
    provides: partner stored shape, platform router and service skeleton, partner_store helpers
  - phase: 87-03
    provides: partner_pool set_pool_size and move_customer, refusal codes partner_suspended and not_found
  - phase: 87-04
    provides: partner_status chokepoint that treats any status other than active as suspended
  - phase: 87-06
    provides: partner_invites.invite and email_in_use (no authorization of their own)
provides:
  - partner_platform_service appoint (with first admin invite), update_partner, suspend, reinstate, partner_customers, direct_customers, move
  - routes PATCH /{id}, POST /{id}/suspend, POST /{id}/reinstate, GET /{id}/customers, GET /direct-customers, POST /customers/{id}/move
  - POST /api/platform/partners now requires adminName and adminEmail and answers {partner, emailSent}
  - audit vocabulary partner.appointed, pool_changed, expiry_changed, ceiling_changed, renamed, suspended, reinstated, customer_moved
affects: [87-09, 87-10, 87-11, 87-12]

actuals:
  tokens: 12900
  tasks: 3
  commits: 6
plan_head_before: 516fe0df9cdb56b7eb970d84ac5cb49b771a92a2
plan_head_after: 72464e8c3128ea9301e60185a845377feffc9716

tech-stack:
  added: []
  patterns:
    - "Validate everything, then run the one step the data can refuse (pool resize), then write the remaining fields, so a refusal leaves no half-applied edit"
    - "Suspension writes the partner document, audits, then revokes sessions per user email; a failed revoke answers 503 but the status stays suspended and a retry finishes the sign-out"
    - "Move target is a required nullable field so an empty body cannot silently mean direct"

key-files:
  created:
    - backend/tests/test_partner_platform.py
    - backend/tests/test_partner_move.py
  modified:
    - backend/partner_platform_service.py
    - backend/partner_platform_endpoints.py
    - backend/tests/test_partner_tracer.py

key-decisions:
  - "A failed appointment invite deletes the new organization and whatever the invite stored (users, invites, invite token row), so no half-appointed partner is left"
  - "Suspend audits before it revokes sessions and always re-runs the revocation, so a retry after a 503 completes the sign-out without a second audit record"
  - "MoveBody.targetPartnerId is required (nullable) rather than defaulting to null"
  - "update_partner runs set_pool_size before writing name, expiry and ceiling, so a refused resize leaves the other fields untouched"

patterns-established:
  - "Raw-handle service functions raise PartnerError; routes return error_response(err), the UI shows body.error verbatim"

requirements-completed: [PART-01, PART-03, PART-06, PART-07]

coverage:
  - id: D1
    description: "Appoint creates the partner and invites its first partner_admin; a clashing email or name is refused before any write; a failed invite leaves nothing behind"
    requirement: PART-01
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_platform.py#test_appoint_invites_the_first_partner_admin"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_platform.py#test_an_email_already_in_use_leaves_no_partner_behind"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_platform.py#test_a_failed_invite_removes_the_partner_it_just_created"
        status: pass
    human_judgment: false
  - id: D2
    description: "List is empty without partners, ordered by name ignoring case then id, with customerCount; an empty ceiling is valid"
    requirement: PART-01
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_platform.py#test_list_orders_by_name_ignoring_case_then_id_and_counts_customers"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_platform.py#test_an_empty_ceiling_is_a_valid_partner"
        status: pass
    human_judgment: false
  - id: D3
    description: "Pool resize accepts the handed-out count and refuses one below with handedOut; expiry set, cleared and expired; ceiling validated and never touches a customer's screens"
    requirement: PART-03
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_platform.py#test_pool_may_equal_the_handed_out_count_but_not_go_below"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_platform.py#test_expiry_can_be_set_cleared_and_reads_expired_once_past"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_platform.py#test_a_ceiling_change_never_alters_a_customers_screens"
        status: pass
    human_judgment: false
  - id: D4
    description: "Suspend signs out every partner user and blocks selling while customers, agents and the pool counter stay byte-for-byte; a failed sign-out is a 503; both verbs are idempotent"
    requirement: PART-01
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_platform.py#test_suspend_locks_the_partner_and_signs_its_users_out"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_platform.py#test_suspend_leaves_every_customer_and_agent_byte_for_byte"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_platform.py#test_a_failed_sign_out_answers_503_and_the_partner_stays_suspended"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_platform.py#test_suspending_twice_or_reinstating_an_active_partner_changes_nothing"
        status: pass
    human_judgment: false
  - id: D5
    description: "Move keeps the seats and moves them between pools (exact fit succeeds, one short is move_does_not_fit), goes direct keeping the licence, comes in from direct, and both lists update at once"
    requirement: PART-07
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_move.py#test_a_move_that_fits_exactly_transfers_the_seats_and_the_customer"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_move.py#test_one_seat_too_few_free_refuses_and_changes_nothing"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_move.py#test_a_move_to_direct_keeps_the_seats_as_the_customers_own_licence"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_move.py#test_after_a_move_the_old_partner_no_longer_lists_the_customer"
        status: pass
    human_judgment: false
  - id: D6
    description: "Direct customers exclude partner organizations, partner customers and platform-admin, ordered by name"
    requirement: PART-07
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_move.py#test_direct_customers_exclude_partners_partner_customers_and_the_platform"
        status: pass
    human_judgment: false
  - id: D7
    description: "Every change and move is audited under platform-admin and each partner involved with before/after or seats/from/to; every route refuses non-Super-Admin callers"
    requirement: PART-07
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_move.py#test_every_move_is_recorded_under_the_platform_and_each_partner"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_platform.py#test_only_the_super_admin_reaches_the_routes"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_move.py#test_only_the_super_admin_reaches_the_customer_routes"
        status: pass
    human_judgment: false
  - id: D8
    description: "Real email delivery of the first-admin invite and the Partners screen that calls these routes"
    human_judgment: true
    rationale: "SMTP is unconfigured on this VM so every test mocks the sender (emailSent false); the screen belongs to a later plan"

duration: 27min
completed: 2026-11-02
status: complete
---

# Phase 87 Plan 08: Super Admin Partner Management Summary

**The Super Admin can appoint a partner and invite its first admin, resize, re-date, re-scope and rename it, suspend and reinstate it without touching its customers, list its customers and the direct ones, and move any customer between partners or to direct with its seats, every step audited and proven on real MongoDB.**

## Performance

- **Duration:** 27 min
- **Tasks:** 3 (6 commits: RED then GREEN per task)
- **Files:** 5 (2 created, 3 modified)

## Accomplishments

- Appoint stores the partner organization, then invites its first `partner_admin` through `partner_invites.invite`; the name, ceiling and email are all checked before the first write, and a failed invite removes the new organization and its leftovers.
- `update_partner` applies only the fields sent (explicit null `expiresAt` clears); the pool floor is D-07's conditional update and runs before the other fields are written; a ceiling change never reads or writes a customer (D-19).
- `suspend` flips only the partner document, audits, then revokes sessions for every partner user email with reason "partner suspended"; customers, agents and the allocated counter are byte-for-byte unchanged. `reinstate` restores active and removes the stamp.
- `partner_customers`, `direct_customers` and `move` (through `partner_pool.move_customer`) with audits under `platform-admin` and each partner involved.

## Task Commits

1. Task 1: RED `36fad4740`, GREEN `00dfcf060`
2. Task 2: RED `33952d292`, GREEN `2b2be96ea`
3. Task 3: RED `676c96cfd`, GREEN `72464e8c3`

## TDD Gate Compliance

Each task has a `test(87-08)` commit that failed before its `feat(87-08)` commit. The RED failures were: Task 1 twelve behavior assertions or missing keys (`emailSent` absent, no user stored) and a missing `update_partner` handler; Task 2 `AttributeError` on the not-yet-existing `suspend_partner` and `reinstate_partner` handlers; Task 3 `AttributeError` on the not-yet-existing `MoveBody`, `get_partner_customers`, `get_direct_customers` and `move_customer`. A missing handler is the planned behavior being absent, but it is an import-level failure, not an assertion failure; the pytest format has no `check tdd-red-evidence` adapter, so the classifier was not run and the semantic assessment above is the only RED evidence. No REFACTOR commits.

## API contract versus services/partnerApi.ts

Consistent with 87-07's client: `appointPartner` reads `{partner, emailSent}`, `updatePartner`/`suspendPartner`/`reinstatePartner` read `.partner`, `fetchPartnerCustomers` and `fetchDirectCustomers` read `.customers`, and `moveCustomer` posts `{targetPartnerId}`. One addition the client does not special-case: suspend can answer 503 with code `sign_out_failed` and body `error` "Couldn't sign this partner's users out. Try again." (the client already shows `body.error` verbatim). The move route answers `{customer: {id, name, partnerId}}`; the client types it as `unknown`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Existing tracer test broke on the new required admin fields**
- **Found during:** Task 1
- **Issue:** `PartnerCreate` now requires `adminName` and `adminEmail` and `appoint` sends a real invite, so `test_partner_tracer.py` (named in Task 1's verify command) could no longer appoint.
- **Fix:** its `_appoint` helper and the 403 test pass an admin name and a per-name email; its `wired` fixture patches `partner_invites.send_invite_email`.
- **Files modified:** backend/tests/test_partner_tracer.py
- **Commit:** `00dfcf060`

**2. [Rule 2 - Critical] Failed invite leaves no half-appointed partner, move target required**
- Beyond the plan's "delete the partner organization": the cleanup also removes the admin user, `invites` record and invite token row; `MoveBody.targetPartnerId` is required so an empty body cannot move a customer out of its partner.
- **Commits:** `00dfcf060`, `72464e8c3`

**Total deviations:** 2 auto-fixed. **Impact:** none on scope.

## Issues Encountered

None. Verification: the three task commands pass (27, 36 and 43 tests). A wider run of every partner and catalogue suite gives 234 passed and 2 failed, exactly the known baseline (`test_sidebar_and_app_agree_with_manifest`, `test_ledger_ratchets`). The private mongod on 27998 was stopped afterwards; the live mongod was never touched and no email was sent.

## Known Stubs

None.

## Threat Flags

None. The new routes sit under the already-mounted `partners` catalogue guard and each handler checks Super Admin itself (T-87-22 to T-87-25 mitigations are all exercised by tests).

## Next Phase Readiness

The Partners screen plan can call every route above. Reminder for it: appoint and suspend need the new response shapes (`emailSent`, 503 `sign_out_failed`).

## Self-Check: PASSED

- backend/partner_platform_service.py, backend/partner_platform_endpoints.py, backend/tests/test_partner_platform.py, backend/tests/test_partner_move.py exist.
- Commits 36fad4740, 00dfcf060, 33952d292, 2b2be96ea, 676c96cfd, 72464e8c3 are on HEAD.
- Acceptance greps: `partner_invites.invite` 1, `revoke_user_sessions` 1, `partner_pool.move_customer` 1, `"/direct-customers"` 1; no `partnerId` inside suspend or reinstate; service 245 and endpoints 138 lines.
