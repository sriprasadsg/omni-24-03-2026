---
phase: 84-staged-patch-rollouts
plan: 20
subsystem: autonomous-ops
status: complete
tags: [patch-rollout, shadow-mode, simulation, stop, gate-06, mongodb, python]

requires:
  - phase: 84-staged-patch-rollouts
    provides: 84-16 resume/cancel, tail pass, Activity texts; 84-13 revert; 84-03 lines; 84-08 reboots
provides:
  - simulation rollouts (rollout.shadow fixed at Start): shadow rows through gate.decide with master_shadow True, host states would_install and would_restart, soak on the real clock, pass without health data
  - live rollout held while the organization is in shadow, released as a new attempt when shadow is lifted
  - rollout field stoppedSince; stop-expired cards given back to their computers and offered again; halt check that ignores them
  - dispatcher refusal (rollout_simulation) and no revert for a simulation
affects: [84-21, 84-22]

requirements-completed: []
requirements-addressed: [PTCH-06, PTCH-05, PTCH-01]

actuals:
  tokens: 12000
  tasks: 2
  commits: 4
commits: 4
plan_head_before: 22d0aa32c56f116ed2d42435355adf5750c7225a
plan_head_after: 97c02d9000a275ab90cd9274d508d1ac85c97c67

tech-stack:
  added: []
  patterns:
    - "lines.shadow_flag(rollout) returns True for a simulation and None for a live rollout (never False, which would switch off the deployment-wide shadow switch); every gate.decide of a rollout passes it as master_shadow"
    - "a shadow row counts the host's attempt, so the first real row after shadow is lifted has a new dedupe key"
    - "stop freeze = decide stays False while stopped, settle still runs, stoppedSince marks the rollout, settle's lineSettled list is what the halt check skips"

key-files:
  created:
    - backend/tests/test_patch_rollout_shadow_stop.py
  modified:
    - backend/autonomous_ops/rollout/controller.py
    - backend/autonomous_ops/rollout/lines.py
    - backend/autonomous_ops/rollout/installs.py
    - backend/autonomous_ops/rollout/reboots.py
    - backend/autonomous_ops/rollout/settle.py
    - backend/autonomous_ops/rollout/dispatcher.py

key-decisions:
  - "A simulation ring has no health data, so it passes on the soak alone: once every computer has a shadow row (would_install or would_restart, or not_reached) the ring moves to soaking with soakEndsAt = that tick + soakHours, then lifecycle.advance. A ring with no computer simulated at all never passes (it waits, the canary retry for not-reached computers still applies)."
  - "A would-restart row is recorded in a simulation only for a computer whose selected packages include a name from the usually-restart-needing families (needs_restart_by_name); there is no agent result to say otherwise. Each computer is tried once (simulatedRestartAt), so a refusal never holds the ring."
  - "A live rollout under shadow keeps its computers at would_install/would_restart and does not advance; when shadow is lifted they go back to waiting (installed for a would-restart; not_reached on a completed rollout) with the shadow row's attempt counted, so the next decision is attempt + 1."
  - "The 're-issue after a stop' is done by the existing settle pass plus the normal decision pass instead of a separate controller re-issue step: settle already returns a cancelled_by_stop row's computer to waiting and bumps its attempt, and now does the same for an expired card whose finishedAt is at or after stoppedSince; the first tick after the stop clears removes stoppedSince and then decides as usual. stoppedSince is the stop's pressedAt (earliest of platform and tenant), else the first tick that saw the stop."

patterns-established:
  - "closed_line(since=..., handled=...) so a halt check can ignore cards that ran out during a stop and cards already offered again"

coverage:
  - id: D1
    description: "A rollout started in shadow mode is a simulation for its whole life: would-install rows ring by ring through gate.decide, ring soak on the real clock, no health data, last ring completes; nothing written to an agent queue, no patch job; lifting shadow later does not turn it live; an approved simulation row is refused at send"
    requirement: PTCH-06
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_shadow_stop.py#test_a_simulation_rollout_records_would_install_rows_ring_by_ring_and_never_touches_a_computer"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_shadow_stop.py#test_lifting_shadow_in_the_middle_never_turns_a_simulation_live"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_shadow_stop.py#test_a_simulation_row_is_never_sent_even_if_it_were_approved"
        status: pass
    human_judgment: false
  - id: D2
    description: "A restart-needing package gets a would-restart row in a simulation; a live rollout whose organization enters shadow records one shadow row per computer and attempt, waits, and decides again as attempt + 1 when shadow is lifted"
    requirement: PTCH-06
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_shadow_stop.py#test_a_package_that_usually_needs_a_restart_gets_a_would_restart_row_in_a_simulation"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_shadow_stop.py#test_a_live_rollout_whose_organization_enters_shadow_records_once_and_waits_until_shadow_is_lifted"
        status: pass
    human_judgment: false
  - id: D3
    description: "During a platform or tenant stop the controller decides and sends nothing and writes no refused row; clearing the stop offers cancelled installs and an approved-then-cancelled line again as attempt 2 with new dedupe keys, the rollout does not halt, and the cancelled instruction and its re-issue never both reach the agent"
    requirement: PTCH-05
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_shadow_stop.py#test_a_stop_freezes_the_canary_and_clearing_it_offers_the_cancelled_installs_again"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_shadow_stop.py#test_an_approved_line_a_stop_cancelled_is_raised_again_as_a_new_approval_and_the_rollout_does_not_halt"
        status: pass
    human_judgment: false
  - id: D4
    description: "A card that expired during a long stop is not a denial: the computer is never read as installed, is offered again after the stop, and the rollout does not halt; an expiry outside a stop still halts with approval_expired; a revert of a halted rollout still goes out during a stop"
    requirement: PTCH-01
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_shadow_stop.py#test_a_line_that_expired_during_a_long_stop_is_raised_again_and_never_halts_the_rollout"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_shadow_stop.py#test_an_expired_line_outside_any_stop_still_halts_the_rollout"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_shadow_stop.py#test_a_revert_of_a_halted_rollout_still_goes_out_during_a_stop"
        status: pass
    human_judgment: false
  - id: D5
    description: "How the Simulation chip, would-install wording and the paused block read on the Rollouts tab, and a real shadow or stop on a live organization"
    requirement: PTCH-06
    verification: []
    human_judgment: true
    rationale: "The screens belong to the UI plans; a real shadow or stop switch is the user's to flip on the live platform"

duration: 15min
completed: 2026-11-07
---

# Phase 84 Plan 20: Shadow Simulation and Stop Behaviour of Rollouts Summary

**A rollout started in shadow mode is a faithful simulation for its whole life (would-install and would-restart rows through the gate, soak on the real clock, nothing ever sent), and a stop freezes a rollout without a refused row, still settles and reverts, and offers cancelled or stop-expired work again as a new attempt without halting.**

## Performance

- **Duration:** about 15 min (plus an 8m40s regression run of 1,458 tests)
- **Tasks:** 2 (both `tdd="true"`)
- **Files:** 1 created, 6 modified (backend only)

## Accomplishments

- **Simulation rollouts (Task 1).** `lines.shadow_flag(rollout)` turns `rollout.shadow` into `master_shadow=True` for every `gate.decide` of the rollout (canary install in `installs.canary_auto`, every approval line in `lines.raise_line`, would-restart rows in `reboots.simulate_restarts`); a live rollout passes `None`, so the deployment-wide switch still applies. A shadow row sets the computer to `would_install` or `would_restart` and counts its attempt; no `patch_deployment_jobs` document and no agent instruction is made. In the controller, a simulation ring records its rows when the window opens, moves to `soaking` with `soakEndsAt = tick time + soakHours`, then passes on the clock alone, and the last ring completes the rollout. `dispatcher.host_problem` answers `rollout_simulation` for any row of a simulation (PROH-84-08, T-84-57), and the controller never starts a revert for one. A live rollout whose organization enters shadow records one shadow row per computer and attempt (the host's `would_*` state stops a second decision), stays in its ring, and when shadow is lifted the computers go back to waiting so the next decision is attempt + 1 with a new dedupe key.
- **Stops (Task 2).** While a platform or tenant stop is on the controller already made no decision (`decide` False), sent nothing and ran reverts through the undo path; this plan adds the `stoppedSince` mark (the stop's press time) on running rollouts and fixes what a stop used to break. A card that expired during a stop (the 24 h clock keeps running, D-13) was read by settle as an installed computer and by the halt check as `approval_expired`. Settle now treats an expired card whose `finishedAt` is at or after `stoppedSince` like a cancelled one (the computer goes back to waiting, attempt + 1), and `lines.closed_line` skips such cards and the ones settle already handled (`lineSettled`). The first pass after the stop clears removes `stoppedSince` and the normal decision pass raises the cards again as attempt 2 (T-84-58, T-84-59).

## Task Commits

1. Task 1 RED: `f6fe9b98e` test(84-20) failing tests for simulation rollouts
2. Task 1 GREEN: `171f416ac` feat(84-20) a rollout started in shadow mode is a simulation for its whole life
3. Task 2 RED: `d4cf5ac8d` test(84-20) failing tests for stops that freeze rollouts without failing them
4. Task 2 GREEN: `97c02d900` feat(84-20) stops freeze rollouts without turning paused work into failures

## TDD Gate Compliance

Both tasks have a RED commit before the GREEN commit. Task 1 RED: all five tests failed on the planned assertions (ring stayed `installing`, no would-restart row, an approved simulation row was queued, live ring 1 recorded no shadow row after the lift). Task 2 RED: three of the new tests failed (`stoppedSince` missing in both stop scopes; the stop-expired card halted the rollout with `approval_expired`); the other stop tests already passed on the code from 84-03/84-13/84-16 and are kept as characterization tests of the stop rules. `gsd_run check tdd-red-evidence` was not run (plan is `type: execute`; pytest output is not one of its formats).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] A card that expired during a stop halted the rollout and its computer read as installed**
- **Found during:** Task 2
- **Issue:** `expire_due` ignores stops (D-13). Settle then found no awaiting row and no unresolved patches and marked the computer `installed` although nothing was installed; the halt check saw the expired row and halted with `approval_expired`.
- **Fix:** `stoppedSince` plus `settle._expired_in_stop` and `lines.closed_line(since, handled)` as described above.
- **Files modified:** controller.py, settle.py, lines.py
- **Commit:** 97c02d900

**2. [Rule 1 - Bug] A shadow row for a revert restart overwrote the computer's state with would_install**
- **Found during:** Task 1
- **Issue:** `lines.raise_line` set `would_install` on the host for every line, including `revert_reboot`, which would have hidden a Reverted computer.
- **Fix:** only the install and reboot lines change the host state (`_SHADOW_STATE`); a revert restart changes none.
- **Commit:** 171f416ac

**3. [Rule 2 - Missing critical] A simulation could still be sent or reverted by a hand-edited or buggy row**
- **Found during:** Task 1
- **Fix:** `dispatcher.host_problem` refuses every row of a simulation rollout (`rollout_simulation`) and the controller skips `revert.tick` and `dispatch_approved` for it (not in the plan's file list for dispatcher.py).
- **Commit:** 171f416ac

**4. [Rule 3 - Interpretation] The plan's separate controller re-issue step is done by settle plus the normal pass**
- **Found during:** Task 2
- **Issue:** the plan describes a controller step that re-issues rows that ended `cancelled_by_stop`. Settle already returns those computers to waiting with their attempt counted (runs every tick, also while stopped), and the normal decision pass then raises or sends them as attempt + 1; a second re-issue step would double-count attempts. Only the expired-during-stop case was missing, so that is what was added to settle.
- **Files modified:** settle.py (not in the plan's file list), lines.py, controller.py
- **Commit:** 97c02d900

**Total deviations:** 4 (2 bugs, 1 missing critical, 1 interpretation). **Impact:** no change to the plan's intent; settle.py and dispatcher.py were touched in addition to the listed files.

## Known Gaps and Edges

- A stop that is pressed and cleared between two controller ticks never records `stoppedSince`; a card that expired in that gap reads as a real expiry and halts the rollout (the ticks run every minute, the stop window would have to be shorter).
- `MAX_ATTEMPTS` (3) counts a stop-cancelled install like an undelivered one: three stops that each cancel the same computer's pending install fail it as not delivered. Rare; not changed because the attempt number is the dedupe key.
- A live rollout in shadow mode still sends rows a person approved before shadow came on (`dispatch_approved`); only new decisions become shadow rows. The plan asked only for the latter.
- A simulation computer that is never online in the window stays `waiting` (or becomes `not_reached`); a simulation ring with no simulated computer never passes.
- Simulation wording on the Rollouts tab (the `Simulation` chip, `Would install` text) already exists in views from earlier plans; no UI file was touched.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register. T-84-57 (`rollout.shadow` fixed at Start, `master_shadow` True on every decide, dispatcher refusal), T-84-58 (no `gate.decide` while stopped; test counts ledger rows across ticks and finds no refused row) and T-84-59 (cancelled instruction terminal at the agent poll, re-issue is attempt 2 with its own dedupe key; test polls the agent) are mitigated and tested.

## Issues Encountered

None open.

## Verification

Private mongod on port 27998 (stopped afterwards):
- Task 1 command: `test_patch_rollout_shadow_stop.py`, `_tracer`, `_lines`: passed (113 with controller, dispatcher, lifecycle, revert), no skips.
- Task 2 command: `test_patch_rollout_shadow_stop.py`, `_revert`, `test_autonomous_ops_stop.py`, `_delivery`: 74 passed, no skips.
- Full regression (`test_patch_rollout_*`, `test_patch_deployment_flow`, `test_autonomous_ops_*`, `test_route_auth_baseline`): 1,458 passed in 8m40s.
- Acceptance: `grep -c master_shadow` installs.py 1, lines.py 5, reboots.py 2; `grep -c stoppedSince` controller.py 7; every file in `autonomous_ops/rollout/` under 500 lines (largest views.py 444); the simulation test asserts zero agent instructions and zero patch jobs at the end; ruff clean.

## Next Phase Readiness

84-21 and 84-22 need nothing new: `controller.tick` keeps its signature. The background loop only calls `tick`; `_tenant` now takes `platform_since` instead of a boolean, and nothing outside the controller calls `_tenant`.

## Self-Check: PASSED
