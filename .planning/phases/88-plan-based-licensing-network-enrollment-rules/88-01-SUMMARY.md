---
phase: 88-plan-based-licensing-network-enrollment-rules
plan: 01
subsystem: licensing
tags: [plans, trial, enrollment, mongodb, fastapi]

requires:
  - phase: 87-partner-channel
    provides: tenant_docs.build_tenant_doc, partner pool seat writers, license_rules.hold_reason
provides:
  - plan_service (stored plans with D-03 defaults, new_tenant_terms, licence_view, is_exempt)
  - plan_trial (the one per-tenant trial record)
  - trial_ended hold reason for new machines of a Free tenant
  - plan-aware GET /api/tenants/{id}/license (D-19 fields)
  - shared enrollment test harness for every 88 enrollment test
affects: [88-02, 88-03, 88-04, 88-05, 88-06, 88-07, 88-11]

actuals:
  tokens: 7000
  tasks: 2
  commits: 1
plan_head_before: 91c85e11d2ee2dd0cb42231f088d71ac785ad24b
plan_head_after: 46d159f5a6346124a21cb8c7d84bcae03d54d060

tech-stack:
  added: []
  patterns:
    - "plan limits are stored documents read at creation and enrollment, with code defaults only when the collection is empty"
    - "trial is one persistent per-tenant record; a missing or unreadable record fails open"

key-files:
  created:
    - backend/plan_service.py
    - backend/plan_trial.py
    - backend/tests/_enrollment_harness.py
    - backend/tests/test_plan_tracer.py
  modified:
    - backend/tenant_docs.py
    - backend/tenant_endpoints.py
    - backend/license_rules.py
    - backend/pending_agents.py
    - backend/tests/test_partner_license_writers.py

key-decisions:
  - "Task 1 (user prerequisite): option-a, the user committed the one-id-per-machine work as 91c85e11d before Task 2"
  - "A trial whose endsAt equals the current instant counts as ended (same >= rule as license_rules.expired)"
  - "Free plan with trialDays None creates a consumed trial; Pro/Enterprise/Custom always create a consumed trial (D-22)"
  - "The harness runs migration 013 after every tenant insert (idempotent) instead of once per database, so a second tenant in the same database gets its Legacy install key"

requirements-completed: [LIC-01, LIC-03, LIC-07]

coverage:
  - id: D1
    description: "Create on a plan stores seats and trial from the plan table; explicit maxAgents is a seatOverride; Custom without seats and unknown plans answer 422"
    requirement: LIC-01
    verification:
      - kind: integration
        ref: "backend/tests/test_plan_tracer.py (test_free_tenant_takes_seats_and_trial_from_the_plan_table, test_explicit_seat_number_is_a_named_override, test_pro_tenant_gets_a_consumed_trial_and_the_pro_seats, test_custom_without_seats_and_unknown_plans_are_refused_and_store_nothing)"
        status: pass
    human_judgment: false
  - id: D2
    description: "After the Free trial ends a new machine is held Pending trial_ended while the enrolled machine re-registers 200 and keeps its seat; platform-admin and missing data are never held"
    requirement: LIC-03
    verification:
      - kind: integration
        ref: "backend/tests/test_plan_tracer.py (test_trial_end_holds_the_next_new_machine_and_leaves_the_enrolled_one_alone, test_platform_admin_is_never_held_trial_ended, test_a_tenant_with_no_plan_and_no_trial_record_is_not_held)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Licence view carries plan, planSeats, seatOverride, partnerManaged, exempt, trial and projected allowedNetworks; daysLeft rounds up and never goes below 0"
    requirement: LIC-07
    verification:
      - kind: integration
        ref: "backend/tests/test_plan_tracer.py (test_licence_view_*, test_days_left_rounds_up_and_never_goes_below_zero)"
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-11-10
status: complete
---

# Phase 88 Plan 01: Plan engine tracer Summary

**The stored plan table now decides a new tenant's seats and Free trial, the end of the trial holds only new machines as `trial_ended`, and the licence route reports plan, seats, trial and learned networks, proven on real MongoDB.**

## Decisions

- Task 1 (checkpoint:decision) resolved as **option-a**: the user committed the prerequisite one-id-per-machine work as commit `91c85e11d` ("feat(agents): one agent id per machine and hardware-bound assets") before Task 2 started. `git ls-files` listed machine_identity.py, asset_identity.py and migration 033 at HEAD. The user's mfa_exempt hunks in authentication_service.py and the collectionIntervals hunk in agent_heartbeat_endpoints.py stay uncommitted on purpose.
- Task 2 (tracer) ran with `<verify>` end to end; it passed, so expansion plans may proceed.

## Accomplishments

- `plan_service.py`: PLAN_KEYS, D-03 defaults (Free 5 seats / 14 days, Pro 50, Enterprise 500, Custom none), stored plans read laid over defaults, `plan_key_of` (missing reads Free), `is_exempt` (platform-admin), `ensure_plans` (never overwrites a changed plan), `new_tenant_terms` (422 `unknown_plan` / `seats_required`), `licence_view`.
- `plan_trial.py`: pure per-tenant trial record (`new_trial`, `consumed_trial`, `ended`, `days_left`, `view`); unreadable or missing record is "no trial", never "ended".
- `create_tenant` takes seats and trial from the plan; an explicit `maxAgents` stores `license.seatOverride`; `build_tenant_doc` gained keyword-only `seat_override` and `trial`.
- `license_rules.hold_reason` returns `trial_ended` right after the licence and partner pool expiry checks; Pending texts for old and new agent builds added.
- `_enrollment_harness.py` (register with a settable client address, `hw`, `tenant`) for every 88 enrollment test; `test_plan_tracer.py` has 19 tests.

## Verification

- Task 2 command: 91 passed, 0 skipped (test_plan_tracer, test_partner_license_writers, test_enrollment_controls, test_pending_agents, test_licensing, test_tenant_license_api, test_machine_identity), on the private mongod at 127.0.0.1:27998.
- Plan-level: test_route_auth_baseline + test_catalogue_route_parity 70 passed. Other suites that touch create/licence code (autonomous_ops_migration, partner_expiry, platform_role_routes, rbac_defaults, sidebar_screen_switches) 87 passed.
- Acceptance greps: 4 defs in plan_service.py, REASON_TRIAL_ENDED x2 in license_rules.py, 0 `license.maxAgents` in plan_service/plan_trial, `"trial"` in the writers test, all new files under 500 lines (pending_agents.py 485).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Harness runs migration 013 after every tenant insert, not once per database**
- **Found during:** Task 2 (writing the harness)
- **Issue:** "once per database" would leave a second tenant in the same database without its Legacy install key, so its registration key would 404.
- **Fix:** `tenant()` runs the idempotent migration after each insert.
- **Files modified:** backend/tests/_enrollment_harness.py
- **Commit:** 46d159f5a

**2. [Rule 3 - Blocking] Commit trailer**
- **Issue:** the first commit carried a Co-Authored-By trailer, which CLAUDE.md and the run notes forbid.
- **Fix:** amended the (unpushed, own) commit to drop it; hash is 46d159f5a.

**Total deviations:** 2 auto-fixed. **Impact:** none on behavior.

## Known Stubs

None.

## Threat Flags

None. T-88-01 (plan name normalized, seat number bounded, create stays Super Admin) and T-88-02 (licence route keeps `_assert_tenant_read`; allowedNetworks projected to cidr, source, addedAt) are implemented and tested.

## Commit hygiene

`backend/tenant_endpoints.py` already carried the user's `agentCollectionIntervals` hunks; only this plan's hunks were staged (patch + `git apply --cached`). Those user hunks remain uncommitted in the working tree.

## Next

Ready for 88-02. Existing production tenants have no `trial` record and so are not held (fail open) until migration 034 (88-11) runs.

## Self-Check: PASSED

- plan_service.py, plan_trial.py, _enrollment_harness.py, test_plan_tracer.py found on disk.
- Commit 46d159f5a is an ancestor of HEAD; 91c85e11d is an ancestor of HEAD.
