---
phase: 87-partner-and-reseller-channel
plan: 03
subsystem: api
tags: [mongodb, seat-pool, compare-and-set, migration, licensing]

requires:
  - phase: 87-01
    provides: partner_pool claim/release/free_seats on the partner sub-document
  - phase: 87-15
    provides: registration drift counts for the partner catalogue entries
provides:
  - partner_pool.change_allotment, set_pool_size, move_customer, reconcile_partner, reconcile_pools, pool_expired
  - migration 029 (partial partnerId/type indexes on tenants, invites tokenHash/email indexes, no backfill)
  - daily reconcile of partner pools on the licensing maintenance tick
  - reclaim_inactive_agents and reconcile_all skip type partner organizations
affects: [87-08, 87-09, 87-10]

actuals:
  tokens: 8000
  tasks: 2
  commits: 3
plan_head_before: 8a72a1d769097741925340f5008170dbe21d98a5
plan_head_after: f007644ecced366581d09f4aedce350aa018f108

tech-stack:
  added: []
  patterns:
    - "Raise claims the pool first and then compare-and-sets the customer; lowering writes the customer first (with an $expr floor on seatsUsed) and then releases"
    - "Reconcile repairs a drift only if it survives a settle pause, because a claim in flight sits ahead of its customer write"

key-files:
  created:
    - backend/migrations/029_partner_channel.py
    - backend/tests/test_partner_pool.py
  modified:
    - backend/partner_pool.py
    - backend/licensing.py
    - backend/app_background_tasks.py
    - backend/tests/test_partner_tracer.py

key-decisions:
  - "Refusal codes: pool_full (free), partner_suspended, changed, below_used (used), pool_below_handed_out (handedOut), move_does_not_fit (free, needed), same_partner, invalid_seats, not_found"
  - "reconcile_partner re-reads after RECONCILE_SETTLE_SECONDS (1.0) before its compare-and-set, so it can never undercount a claim whose customer document is not written yet"
  - "release() runs reconcile_partner when its conditional update matches nothing, as the plan states"

patterns-established:
  - "PartnerError(404, not_found, 'Customer not found') for any customer id not owned by the named partner"

requirements-completed: [PART-03, PART-04, PART-07]

coverage:
  - id: D1
    description: "20 concurrent claims fill a 90/100 pool exactly (10 succeed, allocated 100); 20 concurrent raises 10 to 11 change the customer once and the pool grows by 1"
    requirement: PART-03
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_pool.py#test_twenty_concurrent_claims_fill_the_pool_exactly"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_pool.py#test_twenty_concurrent_raises_of_one_customer_succeed_once"
        status: pass
    human_judgment: false
  - id: D2
    description: "Lowering stops exactly at seatsUsed; a refusal (below_used, pool_full, pool_below_handed_out, move_does_not_fit) changes neither document; a lost compare-and-set returns the claimed seats"
    requirement: PART-03
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_pool.py#test_lowering_stops_exactly_at_the_used_floor"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_pool.py#test_a_lost_compare_and_set_gives_the_claimed_seats_back"
        status: pass
    human_judgment: false
  - id: D3
    description: "Pool resize to exactly allocated succeeds and to allocated - 1 is refused; moves succeed at exactly the free seats, refuse one short, move empty customers, and move to direct"
    requirement: PART-07
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_pool.py#test_pool_can_shrink_to_exactly_what_is_handed_out"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_pool.py#test_move_that_needs_one_more_seat_than_is_free_changes_nothing"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_pool.py#test_moving_to_none_makes_a_direct_customer_and_returns_the_seats"
        status: pass
    human_judgment: false
  - id: D4
    description: "Migration 029 adds indexes only (no partnerId/type backfill) and is idempotent; the licensing loops never read or invent seats for a partner organization"
    requirement: PART-07
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_pool.py#test_migration_029_adds_indexes_only_and_a_second_run_changes_nothing"
        status: pass
      - kind: integration
        ref: "backend/tests/test_partner_pool.py#test_the_licensing_loops_never_read_a_partner_organization"
        status: pass
    human_judgment: false
  - id: D5
    description: "reconcile_pools sets allocated to the true sum with a compare-and-set and reports each drift; wired to the daily licensing tick"
    requirement: PART-04
    verification:
      - kind: integration
        ref: "backend/tests/test_partner_pool.py#test_reconcile_sets_allocated_to_the_true_sum_and_reports_each_drift"
        status: pass
    human_judgment: false
  - id: D6
    description: "The daily tick actually calls reconcile_pools in the running backend (wiring only grep-verified; the loop body is not unit-tested)"
    requirement: PART-04
    human_judgment: true
    rationale: "license_seat_maintenance_loop is an infinite sleep loop; the edit is two lines and confirmed by grep, no test drives a tick"

duration: 15min
completed: 2026-11-02
status: complete
---

# Phase 87 Plan 03: Seat Pool Completion Summary

**Atomic allotment changes with a used-seats floor, pool resize with a handed-out floor, fit-checked moves between partners or to direct, and a settle-guarded counter reconcile on the daily tick, all conditional single-document updates proven on real MongoDB, plus migration 029 (indexes only) and partner organizations excluded from the seat loops.**

## Performance

- **Duration:** about 15 min
- **Completed:** 2026-11-02T18:28:00Z
- **Tasks:** 2
- **Files modified:** 6 (2 created, 4 modified)

## Accomplishments

- `change_allotment`: raise claims the pool then compare-and-sets `license.maxAgents` (lost race releases the claim, 409 `changed`); lowering writes the customer first with an `$expr` floor against `license.seatsUsed` (D-06) and then releases.
- `set_pool_size` is one update conditional on `partner.allocated <= new size` (D-07); `move_customer` claims the target first, compare-and-sets `partnerId` (or unsets it for direct), releases the old pool, and never touches screens, agents or license (D-18, D-19).
- `reconcile_partner` / `reconcile_pools` set `partner.allocated` to the true sum with a compare-and-set, log a WARNING and audit `partner.pool_reconciled` per drift; `release` triggers a reconcile when its counter cannot cover the release.
- Migration 029 and the licensing loop edits; `reclaim_inactive_agents` and `reconcile_all` iterate `{"type": {"$ne": "partner"}}`.
- 26 tests in `test_partner_pool.py`; with the tracer and licensing suites 49 pass on a private mongod, 0 skipped.

## Task Commits

TDD task 1 (RED then GREEN, no refactor needed), task 2 plain:

1. **Task 1 RED:** `3b017b7c6` (test) - 22 of 24 failed, 2 passed (the claim-based cases that already worked)
2. **Task 1 GREEN:** `58109aff8` (feat) - 35 passed (pool + tracer)
3. **Task 2:** `f007644ec` (feat) - 38 passed (pool + licensing)

**Plan metadata:** recorded in the following docs commit.

## TDD Gate Compliance

- RED: `test(87-03)` commit precedes the `feat(87-03)` commits. The target tests failed with `AttributeError: module 'partner_pool' has no attribute ...` for each missing function (and one assertion failure, `5 == 3`, for the release repair). Semantic assessment: these are the planned new public functions, so a missing attribute is the intended reason for failure; no import, collection or fixture fault (the two passing tests exercised existing `claim`). The pytest JUnit report is not one of the formats `check tdd-red-evidence` accepts, and `gsd_run` is not on the shell PATH, so the machine classifier was not run; RED evidence is the console output above.
- GREEN: all passing after the implementation commit. REFACTOR: none.

## Files Created/Modified

- `backend/partner_pool.py` - added pool_expired, change_allotment, set_pool_size, move_customer, reconcile_partner, reconcile_pools (253 lines)
- `backend/migrations/029_partner_channel.py` - indexes only
- `backend/licensing.py` - two loops skip partner organizations
- `backend/app_background_tasks.py` - `reconcile_pools` on the `runs % 24 == 0` branch
- `backend/tests/test_partner_pool.py` - 26 real-MongoDB tests
- `backend/tests/test_partner_tracer.py` - one test adjusted (see deviations)

## Decisions Made

- Refusal codes and their numbers are listed in the frontmatter; later plans (87-08, 87-09, 87-10) call these signatures.
- A refused claim is explained by `_claim_refusal`: a suspended or missing partner gets `partner_suspended` / `not_found`, not a misleading `pool_full`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical] Reconcile settle pause**
- **Found during:** Task 1
- **Issue:** a claim takes pool seats before its customer document is written; a reconcile running in that window would see a sum below the counter, lower it, and the counter would end below the true sum, letting the pool over-allocate (breaks the module invariant and T-87-08).
- **Fix:** `reconcile_partner` re-reads counter and sum after `RECONCILE_SETTLE_SECONDS` (1.0) and repairs only a drift that is identical both times, then compare-and-sets as the plan states. Tests set the constant to 0.
- **Files modified:** backend/partner_pool.py
- **Commit:** 58109aff8

**2. [Rule 1 - Bug] 87-01 tracer test conflicted with release-triggered reconcile**
- **Found during:** Task 1 GREEN
- **Issue:** `test_claim_and_release_are_bounded` claimed 10 seats with no customers and released 99; the plan's required "release reconciles when its update matches nothing" correctly repaired the counter to the true sum 0, so the assertion `free == 4` failed.
- **Fix:** the test now inserts a customer holding 6 seats so the true sum matches (claim 10, release 4, release 99 leaves allocated 6, free 4).
- **Files modified:** backend/tests/test_partner_tracer.py
- **Commit:** 58109aff8

**3. [Rule 2 - Missing critical] Explicit refusals the plan did not name**
- `partner_suspended` (claim refused because the partner is not active) and `not_found` "Partner not found" for a missing target or pool, so a suspension is never reported as a full pool. `same_partner` also covers direct to direct.

**Total deviations:** 3 (1 bug, 2 missing critical). **Impact:** no scope growth beyond the module; behaviours the plan states are unchanged.

## Issues Encountered

- First private mongod start failed to write its pid file because a relative path was used after the fork; restarted with absolute paths.
- The Co-Authored-By trailer suggested by the harness was removed from the RED commit (amended before any further work); project CLAUDE.md forbids it and `.claude/settings.json` sets no `attribution.commit`.

## Verification

- `pytest test_partner_pool.py test_partner_tracer.py` (private mongod 27998): 35 passed. With `test_licensing.py`: 49 passed, 0 skipped. Migration lock/health tests: 10 passed.
- Acceptance: 4 target functions present, 0 transactions, 0 `enabledFeatures` hits, `partner_pool.py` 253 lines; migration has no `update_*`/`delete_`; `reconcile_pools` once in app_background_tasks; `"type": {"$ne": "partner"}` twice in licensing.
- The private mongod was stopped before returning. Migration 029 was not run against the live database (user-owned).

## Known Stubs

None.

## Threat Flags

None beyond the plan's threat model (T-87-07 claim before write, CAS and compensating release; T-87-08 daily reconcile, now settle-guarded; T-87-09 `$expr` floor in the same update). PROH-87-03 holds: no function here touches an agent document or a seat an agent holds (covered by `test_without_the_floor_lowering_below_used_keeps_the_agents_untouched`).

## Next Phase Readiness

- Ready for the remaining wave-3 plans; 87-08/09/10 can call `change_allotment`, `set_pool_size` and `move_customer`.
- Migration 029 is pending the user's run; nothing was restarted, published or pushed.

---
*Phase: 87-partner-and-reseller-channel*
*Completed: 2026-11-02*

## Self-Check: PASSED

- Files present: partner_pool.py, migrations/029_partner_channel.py, tests/test_partner_pool.py
- Commits `3b017b7c6`, `58109aff8`, `f007644ec` are ancestors of HEAD
