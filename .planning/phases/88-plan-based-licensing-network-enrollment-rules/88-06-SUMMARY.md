---
phase: 88-plan-based-licensing-network-enrollment-rules
plan: 06
subsystem: licensing
tags: [trial, free-plan, reminders, seat-override, signup-approval, mongodb]
status: complete

requires:
  - phase: 88-01
    provides: plan_trial record (new_trial, consumed_trial, ends_at, ended, view), the trial_ended hold, plan_service.licence_view
  - phase: 88-02
    provides: licensing.clear_seat_override / set_plan_seats, plan_notices.announce
  - phase: 88-04
    provides: plan_service.change_plan (consumed trial when a tenant has no trial record)
provides:
  - plan_trial.extend, TrialError (codes invalid_days, not_found, not_on_trial, trial_changed), MAX_EXTENSION_DAYS
  - plan_trial.start_for_signup (called by approve_signup), plan_trial.send_trial_reminders, TRIAL_REMINDER_DAYS (7, 1)
  - PATCH /api/tenants/{id}/license fields trialExtendDays and clearSeatOverride; the PATCH now answers the licence view
  - events trial.extended, trial.reminder, and seats.changed from the licence PATCH
affects: [88-10, 88-11, 88-16]

actuals:
  tokens: 24000
  tasks: 2
  commits: 4
plan_head_before: fdf27e6b755ce5c4b401745e86eae4294c19eb06
plan_head_after: 74a5146f4079e136188a71783c7e67788c26b5f5

tech-stack:
  added: []
  patterns:
    - "trial extension is a compare-and-set on the stored trial.endsAt (or on an absent trial record); the loser of a race answers 409 trial_changed"
    - "reminders mirror license_rules.send_expiry_reminders: one atomic $addToSet claim of the due thresholds before anything is posted"
    - "plan_trial stays import-safe: licensing, plan_service, plan_notices, pending_agents are imported inside the async functions"

key-files:
  created:
    - backend/tests/test_trial.py
  modified:
    - backend/plan_trial.py
    - backend/tenant_endpoints.py
    - backend/tenant_signup_endpoints.py
    - backend/app_background_tasks.py

key-decisions:
  - "An extension makes the trial live again: it sets trial.consumed False (and startedAt when it was None), otherwise a tenant that returned to Free after a paid plan (consumed trial) would be extended but never reminded"
  - "The partner organization itself (type partner) and the platform organization are refused with 422 not_on_trial, the same code as a paid plan"
  - "The licence PATCH checks the clearSeatOverride refusals (partner customer 409, Custom 422) before anything is written; the extension then runs before the seat writes so its validation also refuses first"
  - "A tenant first seen inside the last day gets one reminder (the closest threshold) and both thresholds are claimed, as the expiry reminders do"

requirements-completed: [LIC-03, LIC-01]

coverage:
  - id: D1
    description: "Trial extension from the licence PATCH: later of now and the old end plus N days (1..365), reminders cleared, extension recorded with at/by/days/from/to, trial.extended in the ledger, ended trial reopens from now, no trial record starts one; refused 422 not_on_trial for a paid plan or the platform organization with nothing written; concurrent extensions never lose one silently; a Tenant Admin gets 403"
    requirement: LIC-03
    verification:
      - kind: integration
        ref: "backend/tests/test_trial.py (test_an_extension_*, test_extending_*, test_only_a_free_tenant_*, test_two_concurrent_extensions_*, test_a_tenant_admin_cannot_*) against the private mongod"
        status: pass
    human_judgment: false
  - id: D2
    description: "clearSeatOverride returns a direct tenant to its plan's seats (override removed, license and legacy maxAgents written, seats.changed announced); refused 409 for a partner customer and 422 for Custom; a maxAgents set on a direct tenant is stored as the override and announced as seats.changed; a PATCH that moves no seats announces nothing"
    requirement: LIC-01
    verification:
      - kind: integration
        ref: "backend/tests/test_trial.py (test_clearing_*, test_a_seat_number_set_*, test_a_licence_patch_that_changes_no_seats_*)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Approving a self sign-up starts its Free trial (plan's trialDays) and sets its seats from the Free plan; calling again changes nothing; a failing start never undoes the approval; paid plans and tenants that already have a trial are left alone"
    requirement: LIC-03
    verification:
      - kind: integration
        ref: "backend/tests/test_trial.py (test_approving_a_signup_*, test_starting_a_trial_twice_*, test_a_signup_whose_trial_could_not_start_*, test_start_for_signup_leaves_*); test_tenant_signup_approval.py 11 passed"
        status: pass
    human_judgment: false
  - id: D4
    description: "Hourly reminders at 7 and 1 days, once per threshold, to the platform feed and the tenant's admins (audience tag), and for a partner's customer also to the partner's own feed without an audience tag, which notification_audience.reader_filter lets a partner_admin read; none for paid, consumed, ended, platform or far-off trials; re-armed by an extension; license_seat_tick runs the step even when an earlier step raises"
    requirement: LIC-03
    verification:
      - kind: integration
        ref: "backend/tests/test_trial.py (test_reminders_go_out_*, test_a_tenant_first_seen_*, test_paid_consumed_*, test_a_partners_customer_*, test_the_hourly_tick_*)"
        status: pass
    human_judgment: false
  - id: D5
    description: "D-20/D-21/D-22: a trial_ended hold is approved like any hold and the trial stays ended; an ended trial changes no agent status and no enabledFeatures; a tenant back on Free after a paid plan has its next new machine held trial_ended"
    requirement: LIC-03
    verification:
      - kind: integration
        ref: "backend/tests/test_trial.py (test_a_trial_ended_hold_*, test_an_ended_trial_changes_no_agent_status_*, test_a_tenant_back_on_free_*)"
        status: pass
    human_judgment: false
  - id: D6
    description: "Whether the reminder wording reads well to a tenant admin and a partner, and whether the licence panel shows the new fields (the UI is a later plan)"
    requirement: LIC-03
    verification: []
    human_judgment: true
    rationale: "Text quality and panel layout are judgments no test asserts; the UI plan owns the panel"
---

# Phase 88 Plan 06: Trial extension, sign-up start and reminders Summary

**The Free trial now has its whole life: the Super Admin extends it (or returns a seat override to the plan number) from the licence PATCH, a self sign-up's trial starts when it is approved, and the hourly licence job reminds tenant admins (and a partner for its customers) 7 and 1 days before it ends, while an ended trial still stops nothing but new enrollments.**

## Performance

- **Duration:** about 25 min
- **Tasks:** 2 (both TDD: RED commit, then GREEN commit)
- **Files:** 5 (1 created, 4 modified)

## Accomplishments

- `plan_trial.extend(db, tenant_id, days, *, actor, via)`: bounded 1..365, Free-only, one compare-and-set on the stored end, recorded in `trial.extensions` and announced as `trial.extended` (ledger plus an admin notice); returns the new trial view.
- `PATCH /api/tenants/{id}/license` takes `trialExtendDays` and `clearSeatOverride`, announces `seats.changed` whenever a direct tenant's seat number moves, and answers `plan_service.licence_view` (a superset of the old summary, so existing callers keep their keys).
- `plan_trial.start_for_signup` is called by `approve_signup` after the tenant is activated (guarded, logged, never undoes the approval); it writes the trial only when none exists and sets the Free plan's seats (skipping an override).
- `plan_trial.send_trial_reminders` is a new step in `license_seat_tick`, mirroring the expiry reminders (atomic claim, platform feed plus tenant admins, partner feed for a customer).
- `plan_trial.py` is 218 lines and still has no module-level dependency on licensing, plan_service, plan_notices or pending_agents.

## Task Commits

| Step | Commit | Message |
| ---- | ------ | ------- |
| 1 RED | 071ef469c | test(88-06): the Super Admin extends a Free trial and clears a seat override from the licence PATCH |
| 1 GREEN | e6f80fa84 | feat(88-06): the Super Admin extends a Free trial and returns a seat override to the plan's number |
| 2 RED | 21305e83c | test(88-06): a sign-up's trial starts at approval and every Free trial gets its 7-day and 1-day reminders |
| 2 GREEN | 74a5146f4 | feat(88-06): a sign-up's trial starts at approval and every Free trial gets 7-day and 1-day reminders |

## TDD Gate Compliance

- **RED (task 1):** the first test failed on the target behavior (`400 Nothing to update`: the PATCH did not know `trialExtendDays`); the run stopped at the first failure (`-x`). Semantic assessment: a planned-assertion failure, not an import or fixture fault.
- **RED (task 2):** 10 of 26 failed on `module 'plan_trial' has no attribute 'send_trial_reminders'` / `start_for_signup` and the missing hourly step; the 16 others (task 1 tests and the D-20/D-21/D-22 cases that already held from 88-01 and 88-04) passed.
- **GREEN:** both tasks pass after the implementation commits. No REFACTOR commit.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] An extension reopens a consumed trial**
- **Found during:** Task 1 design
- **Issue:** the plan says an extension of an ended trial on Free reopens it from now, but a tenant back on Free after a paid plan carries `consumed: true`, which `send_trial_reminders` skips (as the plan requires). The extension would have worked and the reminders never fired.
- **Fix:** `extend` sets `trial.consumed` False (and `startedAt` when it was None); a trial the Super Admin deliberately grants is a live trial.
- **Files modified:** backend/plan_trial.py
- **Commit:** e6f80fa84

**2. [Design choice within the plan] Refusals and ordering in the licence PATCH**
- `clearSeatOverride` refusals (partner customer 409, Custom 422) run before any write; the extension runs before the seat writes; a `ValueError` from `clear_seat_override` (the platform organization) answers 422. The `seats.changed` announcement compares the seat number before and after the whole PATCH, so it also covers `maxAgents` and the override clear in one place. `tenant_row` also projects `subscriptionTier` to find the plan's number.

**3. [Design choice within the plan] Partner organizations on extend**
- `extend` loads the tenant without the plan's implicit direct-tenant filter and refuses `type: partner` with 422 `not_on_trial`, so the PATCH on a partner organization answers the same text as a paid plan instead of 404.

**Total deviations:** 1 auto-fixed (Rule 2) plus 2 design choices. **Impact:** none on the plan's acceptance criteria.

## Acceptance criteria

- `grep -c "trialExtendDays\|clearSeatOverride" backend/tenant_endpoints.py` = 5 (at least 4); `grep -c "async def extend" backend/plan_trial.py` = 1.
- `grep -c send_trial_reminders backend/app_background_tasks.py` = 1; `grep -c start_for_signup backend/tenant_signup_endpoints.py` = 1; `wc -l backend/plan_trial.py` = 218 (under 500).
- `test_plan_writers_scan.py` and `test_partner_license_writers.py` pass (no new plan or seat writer outside the allowlists).

## Verification

Private mongod on 127.0.0.1:27998, no skipped test:

- Task 1 command (`test_trial.py test_tenant_license_api.py test_partner_license_writers.py test_plan_seats.py`) plus `test_plan_change.py test_plan_writers_scan.py test_plan_tracer.py`: 123 passed.
- Task 2 command (`test_trial.py test_tenant_signup_approval.py test_enrollment_controls.py test_plan_change.py`) plus `test_plan_writers_scan.py test_partner_license_writers.py test_notification_audience_structure.py`: 112 passed.
- Wider regression over every test file that mentions `license_seat_tick`, `plan_trial` or `signup` (includes `test_route_auth_baseline.py`, `test_partner_pool.py`): 231 passed.

## Notes for later plans and the user

- `backend/tenant_endpoints.py` still carries the user's uncommitted `agentCollectionIntervals` hunks (three places); the commit contains only this plan's hunks (the index entry was built from HEAD plus this plan's edits).
- The licence PATCH answer changed from the bare seat summary to the licence view; the UI plan should read `trial` and `plan` from it.
- Nothing was pushed, restarted or published; the reminder step goes live with the next backend restart (88-16).

## Known Stubs

None.

## Threat Flags

None. T-88-16 (existing `manage:tenant_license` gate, bounded days, Free-only, compare-and-set, audit with actor; a Tenant Admin gets 403, tested), T-88-17 (partner feed carries only its own customer's name and date, tenant notice audience-tagged `tenant_admins`, `reader_filter` tested for a partner_admin) and T-88-18 (every extension in `trial.extensions` and the ledger) are mitigated.

## Self-Check: PASSED
