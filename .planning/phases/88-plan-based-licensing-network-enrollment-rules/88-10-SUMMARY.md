---
phase: 88-plan-based-licensing-network-enrollment-rules
plan: 10
subsystem: licensing
tags: [plans, partner-channel, plan-ceiling, trial, customer-rows, mongodb]
status: complete

requires:
  - phase: 88-03
    provides: screen_ceiling.plan_allowed / final_screens used by partner_portal_service._customer_screens
  - phase: 88-04
    provides: plan_service.change_plan(partner_doc=...) with ownership and planCeiling checks
  - phase: 88-06
    provides: plan_trial.new_trial / consumed_trial / extend
provides:
  - partner.planCeiling on partner organizations (Super Admin sets it on appoint and edit; default Free; event partner.plan_ceiling_changed)
  - partner_store.PLAN_CEILING_DEFAULT, plan_ceiling(); partner_summary.planCeiling
  - create_customer with a plan (Free starts the 14-day trial, other plans a consumed one; seats stay the allotment)
  - CUSTOMER_FIELDS now ends with plan and trialEndsAt; overview answers planCeiling
  - PUT /api/partner/customers/{id}/plan and POST /api/partner/customers/{id}/trial (event partner.customer_trial_extended)
  - backend/tests/test_partner_plans.py (24 tests)
affects: [88-11, 88-12, 88-14, 88-16]

actuals:
  tokens: 30000
  tasks: 3
  commits: 6
plan_head_before: 863b14b0fea563ae340316d7957a5fc804e69366
plan_head_after: d110f8f2db058ec33e0bd48b427f46b307d79d3c

tech-stack:
  added: []
  patterns:
    - "partner plan routes delegate to the one writers (plan_service.change_plan, plan_trial.extend) and only map PlanError/TrialError to PartnerError"
    - "a stored planCeiling list is authoritative even when empty (no plan changes); only an absent field falls back to Free (fail closed)"

key-files:
  created:
    - backend/tests/test_partner_plans.py
  modified:
    - backend/partner_platform_service.py
    - backend/partner_platform_endpoints.py
    - backend/partner_store.py
    - backend/partner_portal_service.py
    - backend/partner_endpoints.py
    - backend/plan_service.py

key-decisions:
  - "An empty stored planCeiling means the partner changes no plan; plan_service.change_plan now falls back to Free only when the field is absent (it used `or [\"Free\"]`, which let an empty list change plans to Free)"
  - "trialEndsAt on a customer row is the stored trial end for a Free customer whose trial is not consumed (including one that has already ended, so the partner sees what to extend); None for paid plans, consumed trials and customers with no trial record"
  - "create_customer validates plan name and ceiling before name/email/pool work that writes, and before the pool claim"

requirements-completed: [LIC-02, LIC-03, LIC-04]

coverage:
  - id: D1
    description: "Super Admin sets partner.planCeiling on appoint and edit: canonical keys de-duplicated in order, default ['Free'], 422 invalid_plan with nothing written, change recorded on partner and platform ledgers, same list records nothing, empty list allowed, partner_summary.planCeiling (Free for an old document)"
    requirement: LIC-02
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_plans.py (Task 1 tests, 8) against the private mongod; test_partner_platform.py and test_partner_tracer.py 35 passed"
        status: pass
    human_judgment: false
  - id: D2
    description: "Partner customer creation: starts on Free with a 14-day trial and the allotment as seats (no override), or on another plan inside the ceiling with a consumed trial; outside the ceiling 422 plan_outside_ceiling before the pool claim; unknown plan 422; old partner without a ceiling sells Free only; rows are exactly CUSTOMER_FIELDS ending plan, trialEndsAt; overview planCeiling"
    requirement: LIC-03
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_plans.py (Task 2 tests, 7); test_partner_customers/tracer/isolation/move/ceiling 63 passed"
        status: pass
    human_judgment: false
  - id: D3
    description: "Partner admin changes its customer's plan inside the ceiling (seats unchanged, plan.changed and partner.customer_plan_changed on both ledgers); outside ceiling 422, empty ceiling 422, another partner's customer 404, viewer 403"
    requirement: LIC-02
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_plans.py (test_a_partner_admin_moves_*, test_a_plan_outside_*, test_an_empty_ceiling_*, test_another_partners_customer_*)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Partner admin extends a Free customer's trial 1..365 days (trial.extended on the customer, partner.customer_trial_extended on the partner); Pro customer 422 not_on_trial; 0 and 366 refused by the request model; foreign customer 404; viewer 403"
    requirement: LIC-03
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_plans.py (test_a_partner_admin_extends_*, test_extending_*, test_a_trial_extension_outside_*)"
        status: pass
    human_judgment: false
  - id: D5
    description: "The partner sees each customer's plan and trial end beside its own plan ceiling (data for the picker; the picker itself is a later UI plan)"
    requirement: LIC-04
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_plans.py (test_every_customer_row_*, test_the_overview_shows_the_plan_ceiling_*)"
        status: pass
    human_judgment: true
    rationale: "Whether the picker shows the plan's blocked screens clearly is a UI judgment for the Phase 88 UI plan"
---

# Phase 88 Plan 10: Plans in the partner channel Summary

**The Super Admin now decides which plans each partner may sell (planCeiling, default Free); a partner's new customers start on Free with a 14-day trial (seats stay the allotment); and a partner admin changes its customers' plans within that ceiling and extends their Free trials through the existing audited writers, with the plan and trial end shown on every customer row.**

## Performance

- **Duration:** about 25 min (2026-11-11 02:32 to 02:57 UTC)
- **Tasks:** 3 (all TDD: RED commit, then GREEN commit)
- **Files:** 7 (1 created, 6 modified)

## Accomplishments

- `partner.planCeiling` is set on `POST /api/platform/partners` (default `["Free"]`) and `PATCH /api/platform/partners/{id}`; keys are canonicalised and de-duplicated, an unknown one answers 422 `invalid_plan`, and a real change is recorded as `partner.plan_ceiling_changed` (before, after) on the partner and the platform ledger. `partner_summary` carries `planCeiling`.
- `create_customer(..., plan="Free")` refuses an unknown plan (422 `unknown_plan`) or one outside the ceiling (422 `plan_outside_ceiling`) before the pool claim, stores `subscriptionTier` and a `trial` (running 14-day Free trial from the stored plan table, otherwise consumed), keeps `license.maxAgents` = the allotment with no seat override, and checks the customer's screens against the chosen plan.
- `CUSTOMER_FIELDS` gains `plan` and `trialEndsAt`; rows are still rebuilt key by key. `overview` answers `planCeiling` beside `ceiling`.
- `PUT /api/partner/customers/{id}/plan` calls `plan_service.change_plan(..., via="partner", partner_doc=...)`; `POST /api/partner/customers/{id}/trial` checks ownership and calls `plan_trial.extend(..., via="partner")`, then records `partner.customer_trial_extended` on the partner ledger. Both are partner-admin only.

## Task Commits

| Step | Commit | Message |
| ---- | ------ | ------- |
| 1 RED | 2bb7f4b15 | test(88-10): add failing tests for the partner plan ceiling |
| 1 GREEN | 1d80c0d59 | feat(88-10): the Super Admin sets which plans each partner may sell |
| 2 RED | cc1e11cf1 | test(88-10): add failing tests for plan-aware partner customer creation and rows |
| 2 GREEN | 0d6e98cfb | feat(88-10): a partner's new customer starts on a plan with its trial; rows show plan and trial end |
| 3 RED | 74c9bc616 | test(88-10): add failing tests for partner plan changes and trial extensions |
| 3 GREEN | d110f8f2d | feat(88-10): a partner admin changes its customer's plan and extends its trial |

## TDD Gate Compliance

- **RED (task 1):** 8 of 8 failed on the planned behavior (`planCeiling` not stored or summarized, `partner_store.plan_ceiling` missing, update answering 400 "Nothing to update" because the field is unknown). Failures are the planned assertions, not fixture or collection faults.
- **RED (task 2):** 7 of 15 failed (plan ignored, no trial, rows without plan and trialEndsAt, overview without planCeiling); the 8 task-1 tests passed.
- **RED (task 3):** 9 of 24 failed (`post_customer_trial`, `PlanBody`, `TrialBody` and the routes did not exist); earlier tests passed.
- **GREEN:** each task passes after its implementation commit. No REFACTOR commit.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] An empty stored planCeiling still allowed Free**
- **Found during:** Task 3 (writing the empty-ceiling test; Task 1's behavior says an empty list "means no plan changes")
- **Issue:** `plan_service.change_plan` read the ceiling as `planCeiling or ["Free"]`, so a stored empty list fell back to Free and let a partner move a customer to Free.
- **Fix:** the fallback to Free now applies only when the field is absent or not a list; an empty list refuses every plan. `partner_store.plan_ceiling` follows the same rule.
- **Files modified:** backend/plan_service.py (not listed in the plan's files_modified; 2-line change)
- **Verification:** `test_an_empty_ceiling_lets_a_partner_change_no_plan_even_back_to_free`; test_plan_change.py 37 passed.
- **Commit:** d110f8f2d

**Total deviations:** 1 auto-fixed (Rule 1). **Impact:** none on acceptance criteria; one extra file touched by two lines.

## Acceptance criteria

- Task 1: `grep -c planCeiling` = 5 (partner_platform_service.py), 3 (partner_platform_endpoints.py), 2 (partner_store.py).
- Task 2: `grep -c '"plan", "trialEndsAt"' backend/partner_store.py` = 1; `grep -c plan_outside_ceiling backend/partner_portal_service.py` = 1.
- Task 3: `grep -c` of the two route paths in partner_endpoints.py = 2; partner_portal_service.py 305 lines, partner_endpoints.py 199 lines (both under 500).

## Verification

- Task 1 command: test_partner_plans.py, test_partner_platform.py, test_partner_tracer.py: 43 passed, 0 skipped (private mongod 127.0.0.1:27998).
- Task 2 command: test_partner_plans.py, test_partner_customers.py, test_partner_tracer.py, test_partner_isolation.py, test_partner_move.py, test_partner_ceiling.py: 78 passed, 0 skipped.
- Task 3 command plus route baseline: test_partner_plans.py, test_partner_route_walk.py, test_catalogue_slice_partners.py, test_catalogue_route_parity.py, test_route_auth_baseline.py: 116 passed, 0 skipped.
- Regression: test_plan_change.py, test_plan_writers_scan.py, test_partner_license_writers.py, test_partner_usage.py, test_partner_expiry.py, test_partner_suspension.py all passed (the seat-writer and plan-writer drift scans still find no new writer).

## Notes for later plans and the user

- The UI is untouched: the Super Admin's Partners screen needs a plan-ceiling control and the partner portal needs the plan picker, trial extension and the plan/trial columns (Phase 88 UI plan). New error codes the UI should show verbatim: `invalid_plan`, `unknown_plan`, `plan_outside_ceiling`, `not_on_trial`, `invalid_days`.
- Partners appointed before Phase 88 have no `planCeiling` stored and read as Free only until the Super Admin edits them (A-88-PLAN-CEILING-DEFAULT).
- `trialEndsAt` stays visible after a Free trial has ended (until it is consumed by a plan change), so the partner can see what to extend.
- Nothing was pushed, restarted or published. About 230 other backend files carry the user's uncommitted hunks; none of the files this plan touched were dirty beforehand, so each commit holds only this plan's changes.

## Known Stubs

None.

## Threat Flags

None. T-88-29 (ownership and ceiling checked in change_plan, viewers 403, foreign customer 404, absent ceiling = Free only), T-88-30 (rows still key by key from CUSTOMER_FIELDS; only plan and trialEndsAt added, the trial record never leaves) and T-88-31 (trial.extended on the customer's ledger, partner.customer_trial_extended on the partner's) are mitigated. PROH-88-04: the tenant-scoped routes were not touched; the new routes live under /api/partner and require a partner admin.

## Self-Check: PASSED

Files found: backend/tests/test_partner_plans.py and the six modified modules. Commits found in HEAD ancestry: 2bb7f4b15, 1d80c0d59, cc1e11cf1, 0d6e98cfb, 74c9bc616, d110f8f2d.
