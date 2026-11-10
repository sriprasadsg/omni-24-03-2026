---
phase: 88-plan-based-licensing-network-enrollment-rules
plan: 02
subsystem: licensing
tags: [seats, plans, overrides, partner-pool, mongodb]

requires:
  - phase: 88-01
    provides: plan_service (plans, plan_key_of), the _enrollment_harness, trial_ended hold
provides:
  - licensing.apply_plan_seats, set_plan_seats, set_seat_override, clear_seat_override, raise_direct_seats, _check_seats, EXEMPT_TENANT_ID
  - plan_notices.announce (audit-ledger entry plus admin-only notice, never raises)
  - every manual seat write on a direct tenant stored as license.seatOverride
affects: [88-04, 88-06, 88-11, 88-16]

actuals:
  tokens: 9100
  tasks: 2
  commits: 2
plan_head_before: 8bc23f14e19f74707623eb18b8258723081a9598
plan_head_after: 7f0ef7b90892c1775dfe0bdc87279aa290b57a6e

tech-stack:
  added: []
  patterns:
    - "a direct tenant's license.maxAgents is its plan's seats unless license.seatOverride says a person chose another number; partner customers are decided by the allotment only"
    - "bulk seat edits filter on partnerId/type/platform/seatOverride inside the update itself, so a concurrent override is never overwritten"

key-files:
  created:
    - backend/plan_notices.py
    - backend/tests/test_plan_seats.py
  modified:
    - backend/licensing.py
    - backend/pending_agents.py
    - backend/partner_pool.py
    - backend/tests/test_license_seat_toctou.py
    - backend/tests/test_partner_license_writers.py

key-decisions:
  - "raise_direct_seats uses one find_one_and_update with an aggregation pipeline and caps at MAX_AGENTS_CEILING"
  - "set_seat_override / clear_seat_override / raise_direct_seats refuse (ValueError / LookupError) a partner customer, a partner and the platform organization"
  - "move_customer to direct compares seats with the plan table; a Custom plan (no number) always keeps an override"
  - "announce skips platform-admin (D-26) and takes the actor as dict, token or e-mail string"

requirements-completed: [LIC-01]

coverage:
  - id: D1
    description: "A plan's seat number reaches direct tenants without an override at once and never a partner customer, the platform or an override; overrides (including one equal to the plan's number) survive plan edits; seat numbers are strict whole numbers 0..1,000,000"
    requirement: LIC-01
    verification:
      - kind: integration
        ref: "backend/tests/test_plan_seats.py (test_a_plan_edit_reaches_direct_tenants_and_nothing_else, test_an_override_survives_plan_edits_until_it_is_cleared, test_the_licence_patch_number_is_stored_as_an_override, test_seat_numbers_must_be_whole_numbers_in_range_and_change_nothing, test_a_concurrent_override_and_plan_edit_end_on_the_override)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Lowering a plan keeps running agents and holds only new machines; the seat boundary at enrollment; platform-admin has no limit; 20 racing claims against a plan edit stay within 5..8"
    requirement: LIC-01
    verification:
      - kind: integration
        ref: "backend/tests/test_plan_seats.py (test_lowering_a_plan_keeps_every_running_agent_and_holds_only_new_machines, test_the_next_machine_is_held_at_the_limit_and_enrolls_one_below_it, test_platform_admin_never_runs_out_of_seats); backend/tests/test_license_seat_toctou.py (test_claims_racing_a_plan_edit_never_exceed_the_raised_limit)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Approve-and-raise on a direct tenant stores the override and announces seats.changed (ledger plus admin notice); a partner customer still goes through the pool; moves between direct and partner set or drop the override"
    requirement: LIC-01
    verification:
      - kind: integration
        ref: "backend/tests/test_plan_seats.py (test_approve_and_raise_on_a_direct_tenant_stores_an_override_and_tells_the_admins, test_approve_and_raise_on_a_partner_customer_goes_through_the_pool_and_stores_no_override, test_announce_*, test_moving_a_customer_to_direct_*, test_moving_a_direct_customer_to_a_partner_*, test_a_custom_plan_customer_moved_to_direct_always_keeps_an_override)"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-11-10
status: complete
---

# Phase 88 Plan 02: Plan seats, overrides and the platform exemption Summary

**A direct tenant's seats now follow its plan, a hand-set number (licence PATCH, approve-and-raise, partner-to-direct move) is kept as `license.seatOverride` and survives plan edits, partner allotments and the platform organization are never touched, and the admins are told when a raise changes their limit.**

## Accomplishments

- `licensing.py`: `apply_plan_seats` (one atomic filter that excludes partner customers, partners, platform-admin and overrides, returns the changed ids), `set_plan_seats`, `set_seat_override`, `clear_seat_override`, `raise_direct_seats` (single pipeline update), `_check_seats` (strict int, no bool/float/str, 0..1,000,000), `update_license` stores a PATCHed number as an override, and `EXEMPT_TENANT_ID` makes `try_claim_seat` always succeed and `seats_available` answer the ceiling for platform-admin.
- `plan_notices.announce`: one hash-chained ledger entry plus an admin-audience notice; each write fails independently and never raises; the platform organization gets none.
- `pending_agents.approve` (direct branch) uses `raise_direct_seats` and announces `seats.changed` with before/after and the actor; the partner-customer branch is unchanged.
- `partner_pool.move_customer`: to direct keeps the seats as an override unless they equal the plan's number (Custom always keeps one); to a partner drops the override.
- Tests: 28 in `test_plan_seats.py` on real MongoDB plus a 20-claim race against a plan edit in `test_license_seat_toctou.py`.

## Verification

- Task 1 command: 58 passed, 0 skipped. Task 2 command: 107 passed, 0 skipped. Plan-level (test_plan_tracer, test_enrollment_controls plus both sets): 158 passed, 0 skipped, on the private mongod at 127.0.0.1:27998.
- Wider sweep (every test_*partner*, *pending*, *license*, *tenant* file): 443 passed, 1 skipped (`test_tenant_isolation.py:194`, a mock-free Mongo check that targets the default port; not part of this plan's commands).
- Acceptance: 5 seat functions in licensing.py; `"partnerId": {"$exists": False}` present twice (checked with `grep -F`; the plan's escaped BRE form returns 0 only because of shell/regex quoting); licensing.py 352 lines, pending_agents.py 490 lines; `raise_direct_seats` 1x and `"$inc": {"license.maxAgents"` 0x in pending_agents.py; `seatOverride` 4x in partner_pool.py.
- PROH-88-06 (a plan edit must not change a partner customer's seats or the platform's): covered by `test_a_plan_edit_reaches_direct_tenants_and_nothing_else` and the partner-move tests.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Drift guard still required pending_agents.py to write license.maxAgents**
- **Found during:** Task 2 verification
- **Issue:** `test_only_the_allowlisted_modules_write_license_max_agents` asserts `SEAT_WRITERS_KNOWN <= found`; after the approve-and-raise change `pending_agents.py` no longer writes the field itself (it goes through licensing), so the scanner correctly stopped seeing it.
- **Fix:** removed `pending_agents.py` from `SEAT_WRITERS_KNOWN` (it stays in the allowlist, as the plan says).
- **Files modified:** backend/tests/test_partner_license_writers.py
- **Commit:** 7f0ef7b90

**2. [Rule 1 - Bug] `_direct_filter(tenant_id)` let platform-admin through the by-id writers**
- **Found during:** Task 1 (`test_set_plan_seats_skips_...`)
- **Issue:** naming the tenant id replaced the platform exclusion, so `set_plan_seats` changed platform-admin.
- **Fix:** the by-id filter is `{"$eq": id, "$ne": "platform-admin"}`.
- **Commit:** e3d959da6

**3. [Process] Tests were written after the implementation**
- Task 1 and Task 2 code was written first and the tests second, so there is no separate RED commit. The tests were still written to the behavior list and caught deviation 2 above. Impact: none on behavior.

**Total deviations:** 2 auto-fixed bugs, 1 process note. **Impact:** none on scope.

## Commit hygiene

`backend/tests/test_license_seat_toctou.py` already carried the user's uncommitted `import sys` / `import os` split; only this plan's appended test was staged (blob written with `git hash-object` and `git update-index --cacheinfo`), so the user's hunk stays uncommitted in the working tree. No Co-Authored-By trailer on either commit.

## Known Stubs

None.

## Threat Flags

None. T-88-04 (filter excludes partner customers, partners, platform and overrides; tested with a partner customer and the platform on the same plan), T-88-05 (one pipeline update writes number and override; the existing `manage:tenant_license` check in the endpoint is unchanged) and T-88-06 (every raise records who, from and to in the tenant's ledger) are implemented and tested.

## Next

Ready for 88-03 (same wave) and 88-04, which calls `set_plan_seats` / `apply_plan_seats` from the plan routes. Nothing here is deployed: the backend must be restarted by the user (88-16) before the new behavior is live.

## Self-Check: PASSED

- backend/plan_notices.py and backend/tests/test_plan_seats.py found on disk.
- Commits e3d959da6 and 7f0ef7b90 are ancestors of HEAD.
