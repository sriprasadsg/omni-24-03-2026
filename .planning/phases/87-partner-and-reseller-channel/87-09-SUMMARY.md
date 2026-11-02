---
phase: 87-partner-and-reseller-channel
plan: 09
subsystem: api
tags: [fastapi, mongodb, partner-channel, seat-pool, screen-ceiling, invites, isolation]

requires:
  - phase: 87-01
    provides: partner_portal_service/partner_endpoints skeleton, current_partner, customer_rows, CUSTOMER_FIELDS
  - phase: 87-03
    provides: partner_pool.change_allotment, pool_expired, refusal codes
  - phase: 87-06
    provides: partner_invites.invite, resend, member_status, email_in_use (no authorization of their own)
  - phase: 87-08
    provides: the invite-failure cleanup pattern
provides:
  - partner_portal_service create_customer (with first-admin invite), change_seats, customer_features, set_customer_features, team, invite_colleague, resend_colleague
  - routes PUT /api/partner/customers/{id}/seats, GET/PUT /customers/{id}/features, GET/POST /team, POST /team/{user_id}/resend
  - POST /api/partner/customers now requires adminName and adminEmail and answers {customer, emailSent}
  - tenant_features.SWITCH_LABELS
  - audit vocabulary partner.customer_created, invite_sent, allotment_changed, customer_screens_changed
affects: [87-10, 87-11, 87-12, 87-13, 87-14]

actuals:
  tokens: 14970
  tasks: 3
  commits: 6
plan_head_before: 4e5cb511aa16f50360ccb18e590d6c19159b595d
plan_head_after: 35053f72c4787a1ee4e7c6ec2f72f1426fb2f59d

tech-stack:
  added: []
  patterns:
    - "Validate everything that needs no write (expired pool, email, name, screens), then claim, store, invite; a failed invite deletes the customer and what the invite stored, then returns the seats"
    - "Screens: submitted order de-duplicated, then kept screens outside the ceiling, then missing start screens; written as a compare-and-set on the list that was read"
    - "A foreign customer id and an unknown id are indistinguishable (same filter {id, partnerId} and one not_found body)"

key-files:
  created:
    - backend/tests/test_partner_customers.py
    - backend/tests/test_partner_ceiling.py
    - backend/tests/test_partner_isolation.py
    - backend/tests/test_partner_usage.py
  modified:
    - backend/partner_portal_service.py
    - backend/partner_endpoints.py
    - backend/tenant_features.py
    - backend/tests/test_partner_tracer.py

key-decisions:
  - "A kept screen the customer already has may be re-sent even when it is not in the switch vocabulary (view:tickets is not a switch); 'all' is refused always, even if the customer holds it"
  - "Kept screens are exempt from the missing-parent check, so a legacy customer state never blocks every later save"
  - "The screens write compares-and-sets on the list that was read; a concurrent Super Admin change answers 409 changed instead of being overwritten"
  - "ensure_tenant_extras runs after the invite succeeds, so a failed invite leaves no autonomy-settings row to clean up"
  - "Team routes (GET included) need a partner admin; ColleagueInvite.role is a Literal, so a bad role over HTTP is FastAPI's 422, while the service raises invalid_role"

patterns-established:
  - "_require_partner_admin(user, what) names the action in its 403"

requirements-completed: [PART-02, PART-03, PART-04, PART-05, PART-06, PART-08]

coverage:
  - id: D1
    description: "Create a customer from the pool with its first admin invited as Tenant Admin/customer_admin; answer is {customer, emailSent} with no token, link or registrationKey; a created customer carries no type"
    requirement: PART-02
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_customers.py#test_creating_a_customer_invites_its_first_admin_and_returns_no_secret"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_customers.py#test_a_created_customer_is_never_a_partner"
        status: pass
    human_judgment: false
  - id: D2
    description: "A used or invalid admin email is refused before the pool is touched; a failure after the customer is stored deletes it and returns its seats"
    requirement: PART-02
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_customers.py#test_an_email_in_use_anywhere_is_refused_before_the_pool_is_touched"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_customers.py#test_a_failed_invite_deletes_the_customer_and_returns_its_seats"
        status: pass
    human_judgment: false
  - id: D3
    description: "Names are unique across all organizations ignoring case and spaces with one generic refusal; stored names keep their letters, non-ASCII included"
    requirement: PART-05
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_customers.py#test_a_name_in_use_by_any_organization_is_refused_generically"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_customers.py#test_non_ascii_names_are_stored_with_their_own_letters_and_collide_ignoring_case"
        status: pass
    human_judgment: false
  - id: D4
    description: "An expired pool refuses creation and raising seats every time with the D-08 messages and never moves allocated; lowering stays allowed"
    requirement: PART-04
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_customers.py#test_an_expired_pool_refuses_every_creation_and_never_moves_the_counter"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_customers.py#test_an_expired_pool_refuses_raising_seats_every_time_but_allows_lowering"
        status: pass
    human_judgment: false
  - id: D5
    description: "Seats lower to exactly the seats in use (below_used with used otherwise) and raise only within free seats (pool_full with free otherwise)"
    requirement: PART-03
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_customers.py#test_seats_lower_to_exactly_the_seats_in_use_and_not_below"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_customers.py#test_seats_raise_only_within_the_free_seats"
        status: pass
    human_judgment: false
  - id: D6
    description: "Customer screens only within the ceiling plus start screens; one string beyond is refused naming the screen; kept screens survive; all, unknown strings and a missing parent are refused; order is submitted, kept, missing start"
    requirement: PART-06
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_ceiling.py#test_a_list_equal_to_the_ceiling_plus_the_start_screens_is_accepted"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_ceiling.py#test_one_string_beyond_the_ceiling_is_refused_naming_the_screen"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_ceiling.py#test_screens_outside_the_ceiling_the_customer_already_has_are_kept"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_ceiling.py#test_all_and_unknown_strings_are_refused"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_ceiling.py#test_a_switch_whose_parent_is_missing_is_refused_naming_both"
        status: pass
    human_judgment: false
  - id: D7
    description: "Viewer gets 403 on every write route and on GET /team, and may read /features; partner A using B's, a direct customer's or a partner's id answers the same 404 as an unknown id and changes nothing"
    requirement: PART-05
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_isolation.py#test_another_partners_ids_answer_the_same_404_as_an_unknown_id_and_change_nothing"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_isolation.py#test_a_viewer_cannot_read_or_change_the_team"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_customers.py#test_a_viewer_cannot_create_or_change_seats"
        status: pass
    human_judgment: false
  - id: D8
    description: "Overview lists only the partner's customers with exactly the D-01 keys and no secret anywhere; an empty partner reads customers [] and its pool; pool, seats, agent counts, expiry and ordering follow the PART-08 rules"
    requirement: PART-08
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_isolation.py#test_a_partner_overview_lists_only_its_own_customers_with_exactly_the_d01_keys"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_usage.py#test_each_row_counts_seats_and_agents_by_the_licence_and_status_rules"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_usage.py#test_the_licence_expiry_is_the_earlier_of_the_customers_and_the_pools"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_usage.py#test_customers_are_ordered_by_name_ignoring_case_then_id"
        status: pass
    human_judgment: false
  - id: D9
    description: "Team: lists only this partner's staff with active, invited or invite_expired; invites partner_admin or partner_viewer; resend only before a password is set and only inside the partner; never a token"
    requirement: PART-02
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_isolation.py#test_the_team_lists_only_this_partners_staff_with_their_invite_status"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_isolation.py#test_resend_works_only_before_a_password_is_set_and_only_inside_the_partner"
        status: pass
    human_judgment: false
  - id: D10
    description: "A hand-out whose expiry check ran before the pool's expiry instant may still commit"
    human_judgment: true
    rationale: "Accepted backstop in the plan; the check reads the partner document loaded at request start and no test races the clock"
  - id: D11
    description: "Real invite email delivery and the Partner portal screens that call these routes"
    human_judgment: true
    rationale: "SMTP is unconfigured on this VM and every test mocks the sender; the screens belong to later plans"

duration: about 35 min
completed: 2026-11-02
status: complete
---

# Phase 87 Plan 09: Partner Portal Customers, Seats, Screens and Team Summary

**A partner admin can create a customer from its pool with its first admin invited, change its seats between the seats in use and the pool's free seats, tick its screens only within the ceiling (keeping what the customer already had), and invite its own colleagues, with a two-partner test showing nothing crosses and nothing beyond the D-01 fields leaves.**

## Performance

- **Duration:** about 35 min (start time not recorded; estimated from the commit times)
- **Tasks:** 3 (6 commits, RED then GREEN per task)
- **Files:** 8 (4 created, 4 modified)

## Accomplishments

- `create_customer` refuses an expired pool, a bad or used email and a clashing name before any write, then claims, stores and invites; a failed invite removes the customer, its users, invite rows and token, and returns the seats. The answer is `{customer, emailSent}`.
- `change_seats` is `partner_pool.change_allotment(enforce_used_floor=True, require_active=True)` plus the D-08 hand-out refusal on an expired pool; lowering stays allowed.
- `set_customer_features` and `create_customer` share one validator; `tenant_features.SWITCH_LABELS` names screens in refusals.
- `team`, `invite_colleague`, `resend_colleague` plus routes; all team routes need a partner admin.
- 43 new tests across four modules on real MongoDB; `test_partner_route_walk.py` still passes (15) with the new routes.

## Task Commits

1. Task 1: RED `3d36de332`, GREEN `b797f7aea`
2. Task 2: RED `43852edb8`, GREEN `8255e0546`
3. Task 3: RED `15e741793`, GREEN `35053f72c`

## TDD Gate Compliance

Each task has a `test(87-09)` commit before its `feat(87-09)` commit. RED evidence by task: Task 1 twelve of fifteen tests failed (`put_customer_seats` and `SeatsBody` absent, and no invite stored); Task 2 all twelve failed (`SWITCH_LABELS`, `put_customer_features` absent); Task 3 five failed (`get_team`, `post_colleague`, `ColleagueInvite` absent). The missing-handler failures are import-level `AttributeError`s, not assertion failures, and the pytest format has no `check tdd-red-evidence` adapter, so the classifier was not run; this paragraph is the only RED evidence. In Task 3, `test_partner_usage.py` and the overview and 404 tests in `test_partner_isolation.py` passed as soon as they were written, because `partner_store.customer_rows` and the `{id, partnerId}` filters already existed from 87-01 and 87-03; they lock that behaviour rather than drive new code. No REFACTOR commits.

## API contract versus services/partnerApi.ts

Consistent with 87-07's client: create answers `{customer, emailSent}` (201); seats answers `{customer, pool}` (the client reads `.customer`); features GET and PUT answer `{enabledFeatures, ceiling, unrestricted, kept}`; team answers `{members}`; invite answers `{member, emailSent}` (member `{id, name, email, role, status}`); resend answers `{member, emailSent}`. Additions the client does not special-case: refusals carry `code` and extra numbers (`used`, `free`, `screen`, `parent`), and screens can answer 409 `changed`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Existing tracer tests broke on the new required admin fields**
- **Found during:** Task 1
- **Issue:** `CustomerCreate` now requires `adminName` and `adminEmail`, so nine `pe.CustomerCreate(...)` calls in `test_partner_tracer.py` (named in Task 1's verify command) could not validate.
- **Fix:** a `_new(name, seats)` helper supplies a distinct admin email per call.
- **Files modified:** backend/tests/test_partner_tracer.py
- **Commit:** `b797f7aea`

**2. [Rule 1 - Bug] Re-sending a kept screen was refused as unknown**
- **Found during:** Task 2 (own test)
- **Issue:** a screen the customer already holds outside the switch vocabulary (for example `view:tickets`) failed `invalid_screen` when sent back.
- **Fix:** kept screens count as known, except `all`, which is always refused.
- **Files modified:** backend/partner_portal_service.py
- **Commit:** `8255e0546`

### Other differences from the plan text

- `ensure_tenant_extras` runs after the invite succeeds rather than before it, so a failed invite leaves no autonomy-settings row behind.
- The screens write is a compare-and-set on the list that was read (409 `changed`), which the plan did not ask for; it protects a concurrent Super Admin change (D-19).
- Kept screens are exempt from the missing-parent check.

**Total deviations:** 2 auto-fixed, 3 minor differences. **Impact:** none on scope.

## Issues Encountered

None blocking. `git diff -- backend/tenant_endpoints.py` shows 11 changed lines; they are the user's pre-existing uncommitted hunk (the file was dirty before this plan) and this plan did not touch the file.

## Verification

- Task commands: customers + tracer 26 passed; ceiling + tenant_feature_switches + sidebar_screen_switches 58 passed; isolation + usage + customers + catalogue_slice_partners 32 passed (private mongod 27998, no skips).
- `test_partner_route_walk.py`: 15 passed.
- Wider run (`test_partner_*`, catalogue manifest, route parity, slice partners, rbac_defaults, tenant switch suites): 367 passed, 2 failed, exactly the known baseline (`test_sidebar_and_app_agree_with_manifest`, `test_ledger_ratchets`).
- Acceptance greps: `registrationKey` 0 in service and endpoints; `partner_invites.invite` 1; `SWITCH_LABELS` 1 in tenant_features.py; the only `tenant_id` hit in partner_endpoints.py is the `current_partner` lookup; service 254 and endpoints 168 lines.
- The private mongod was stopped; the live mongod was never touched; no email was sent; the backend was not restarted.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register: T-87-26 (every lookup filters `{id, partnerId}`; foreign, direct, partner and unknown ids answer one 404), T-87-27 (server-side ceiling, `all` refused), T-87-28 (rows rebuilt from CUSTOMER_FIELDS; tests walk every answer for forbidden keys and seeded secrets), T-87-29 (resend limited to the caller's partner, partner roles only, before a password is set), T-87-30 (one generic name refusal) are each exercised by a test.

## Next Phase Readiness

The portal API is complete for the UI plans. Note for them: the customer-admin invite uses role `Tenant Admin`; `GET /team` is partner-admin-only, so a viewer's Team tab must not call it.

## Self-Check: PASSED

- Created: backend/tests/test_partner_customers.py, test_partner_ceiling.py, test_partner_isolation.py, test_partner_usage.py exist.
- Commits 3d36de332, b797f7aea, 43852edb8, 8255e0546, 15e741793, 35053f72c are on HEAD.
