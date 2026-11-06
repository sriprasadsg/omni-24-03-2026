---
phase: 84-staged-patch-rollouts
plan: 22
subsystem: autonomous-ops
status: complete
tags: [patch-rollout, controller-loop, distributed-lock, migration, mongodb, python]

requires:
  - phase: 84-staged-patch-rollouts
    provides: 84-01 controller.tick, store.ensure_indexes and the tracer fixtures
provides:
  - migration 031 creating the rollout indexes (one_active_rollout_per_host, tenant_rollout_ring, tenant_status, id_unique) through store.ensure_indexes, indexes only
  - rollout/loop.py run_once (renewed lock patch_rollout_controller, claim-index guard, tick with lost()) and rollout_loop (PATCH_ROLLOUT_INTERVAL_SEC, default 60)
  - the loop started with the backend as the task patch_rollout_controller beside the Autonomous Ops sweep
affects: [84-03, 84-04, 84-16]

requirements-completed: [PTCH-01, PTCH-07]

actuals:
  tokens: 9500
  tasks: 2
  commits: 4
commits: 4
plan_head_before: 9ae72cd4e5f3060bb15de6da3363c5a4e7eb4666
plan_head_after: d23554c317db916d1493650189848347493a2b7f

tech-stack:
  added: []
  patterns:
    - "the loop lives in its own module and reads controller.tick as a module attribute, so a reload (or a test patch) is picked up and controller.py is never edited here"
    - "index guard copies the sweep: a missing index is made again, only an index that cannot be made stops the pass"

key-files:
  created:
    - backend/migrations/031_patch_rollouts.py
    - backend/autonomous_ops/rollout/loop.py
    - backend/tests/test_patch_rollout_controller.py
  modified:
    - backend/app_startup.py

key-decisions:
  - "run_once returns None (not a zero-count dict) when the claim index is missing and cannot be made, as the plan states; the sweep returns {'tenants': 0} in that case"
  - "The loop is its own module (rollout/loop.py) instead of part of controller.py because 84-03 edits controller.py in the same wave (A-84-SPLIT)"

coverage:
  - id: D1
    description: "Migration 031 creates the unique partial claim index and the lookups, a second run changes no index, it backfills and deletes nothing, and the runner discovers it as 031"
    requirement: PTCH-07
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_controller.py#test_migration_creates_the_claim_index_and_the_lookups"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_controller.py#test_running_the_migration_twice_changes_no_index"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_controller.py#test_the_migration_backfills_and_deletes_nothing"
        status: pass
      - kind: unit
        ref: "backend/tests/test_patch_rollout_controller.py#test_the_runner_discovers_migration_031"
        status: pass
    human_judgment: false
  - id: D2
    description: "Only one controller ticks at a time; a held lock gives None and no tick; the tick gets lost(); the lock is released afterwards"
    requirement: PTCH-07
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_controller.py#test_a_held_lock_makes_run_once_return_none_and_run_no_tick"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_controller.py#test_only_one_controller_ticks_at_a_time_and_the_lock_is_released"
        status: pass
    human_judgment: false
  - id: D3
    description: "The controller never runs without the claim index: a missing index is made again; duplicate active claims stop the pass with an error naming the index and no tick"
    requirement: PTCH-07
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_controller.py#test_a_missing_claim_index_is_made_again_and_the_tick_runs"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_controller.py#test_a_claim_index_that_cannot_be_made_stops_the_pass"
        status: pass
    human_judgment: false
  - id: D4
    description: "After the rollout modules are reloaded (a restart), the next pass continues the installing rollout from stored state and writes no second instruction or ledger row"
    requirement: PTCH-01
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_controller.py#test_a_restart_resumes_the_rollout_from_stored_state_without_a_second_instruction"
        status: pass
    human_judgment: false
  - id: D5
    description: "rollout_loop logs a failing pass and goes on, re-raises CancelledError, reads PATCH_ROLLOUT_INTERVAL_SEC (default 60, bad values ignored) and is started beside the sweep as patch_rollout_controller"
    requirement: PTCH-01
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_controller.py#test_the_loop_logs_a_failing_pass_goes_on_and_re_raises_cancellation"
        status: pass
      - kind: unit
        ref: "backend/tests/test_patch_rollout_controller.py#test_the_interval_reads_the_env_name_defaults_to_60_and_ignores_a_bad_value"
        status: pass
      - kind: unit
        ref: "backend/tests/test_patch_rollout_controller.py#test_the_backend_starts_the_rollout_loop_beside_the_sweep"
        status: pass
    human_judgment: false
---

# Phase 84 Plan 22: Controller loop and migration 031 Summary

**A locked, index-guarded background loop around the rollout controller tick, started with the backend, plus migration 031 that creates the one-active-rollout-per-host index.**

This plan is the loop task 84-01 held before its first revision (A-84-SPLIT).

## Performance

- **Duration:** about 20 min
- **Started:** 2026-11-06T15:36Z
- **Completed:** 2026-11-06T15:57Z
- **Tasks:** 2 (each run test-first: RED commit, then GREEN commit)
- **Files:** 4 (3 created, 1 modified)

## Accomplishments

- Migration 031 calls `store.ensure_indexes`; indexes only, a repeat run is a no-op, nothing is backfilled or deleted.
- `rollout/loop.py` (85 lines): `run_once` takes `lock_with_renewal` on `patch_rollout_controller` (TTL 120 s, renewed every 30 s), returns None when another copy holds it or when the claim index is missing and cannot be made, otherwise runs `controller.tick(db, now=now, lost=lambda: handle.lost)`. `rollout_loop` repeats it every `PATCH_ROLLOUT_INTERVAL_SEC` (default 60).
- `app_startup.run_startup_services` starts the loop through `_safe_bg_task` right after the Autonomous Ops sweep.
- 12 new tests; the whole rollout set plus the structural, sweep, migration and copy-gate tests pass on a private mongod (266 passed, 0 skipped).

## Task Commits

1. Task 1 RED: `910821e7f` test(84-22): migration 031 creates the rollout indexes and changes nothing else
2. Task 1 GREEN: `e0acfccd6` feat(84-22): migration 031 creates the one-active-rollout-per-host index and the rollout lookups
3. Task 2 RED: `46d64ed4a` test(84-22): the rollout loop runs one copy at a time, needs the claim index and resumes after a restart
4. Task 2 GREEN: `d23554c31` feat(84-22): the rollout controller loop runs under a renewed lock, needs the claim index and starts with the backend

## Decisions Made

- `run_once` returns None when the index cannot be made (plan wording), unlike the sweep's `{"tenants": 0}`.
- The restart test reloads every rollout module in dependency order with `importlib.reload`; the full rollout suite still passes afterwards in the same process.

## Deviations from Plan

None - plan executed exactly as written. `backend/app_startup.py` carried no uncommitted user hunks, so the whole file diff (6 added lines) was staged. `controller.py` was not touched and no tick fault was found, so there is no finding for 84-03.

## Issues Encountered

None.

## Known Stubs

None.

## Threat Flags

None. T-84-62 (lock plus `lost()`), T-84-63 (claim index guard plus migration) and T-84-64 (logged pass errors, `CancelledError` re-raised, `_safe_bg_task`) are mitigated and tested.

## User Setup Required

None for the code. Migration 031 was only run against a private test database. It reaches the live database through the migration runner on the next backend restart, and the loop starts at that restart too; both are the user's. The loop also makes the claim index itself if the migration has not run.

## Next Phase Readiness

Ready for the remaining wave work. After the wave, re-run `test_patch_rollout_tracer.py` and `test_autonomous_ops_structural.py` on the merged code (done here on the current tree: pass).

## Self-Check: PASSED

- backend/migrations/031_patch_rollouts.py, backend/autonomous_ops/rollout/loop.py, backend/tests/test_patch_rollout_controller.py: found.
- Commits 910821e7f, e0acfccd6, 46d64ed4a, d23554c31: found in history.
- Acceptance greps: ensure_indexes 1, write calls in migration 0, rollout_loop 2, patch_rollout_controller 2, lock_with_renewal present, loop.py 85 lines, no commit touched controller.py.
