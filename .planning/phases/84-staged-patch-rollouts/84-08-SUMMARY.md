---
phase: 84-staged-patch-rollouts
plan: 08
subsystem: autonomous-ops
status: complete
tags: [patch-rollout, health-gate, reboot, boot-baseline, services, not-reached, mongodb, python]

requires:
  - phase: 84-staged-patch-rollouts
    provides: 84-01 controller, settle, health.ring_verdict; 84-03 approval lines, dispatcher, halt; 84-02 messages
provides:
  - reboots.py - Reboot line (one reboot_host row per installed computer whose result says a restart is needed), record_baseline, is_new_boot, overdue, and settle of restarting computers (new boot -> healthy, undelivered -> asked again, 30 min after due -> failed no_new_boot)
  - signals.py - host_signals reading install, inventory, heartbeat and services from data newer than the change; not_checked and agent_only values
  - health.py - complete pure ring_verdict (integer failure share, named first failing computer, no_reports, canary_os, not_reached excluded), health_rows, last_change
  - controller - restart phase before the soak, early halt on failure, ring health rows, not-reached tracking per window occurrence, canary retry of a not-reached computer
affects: [84-09, 84-10, 84-13, 84-16, 84-18]

requirements-completed: [PTCH-02, PTCH-03, PTCH-01, PTCH-06]

actuals:
  tokens: 21000
  tasks: 3
  commits: 5
commits: 5
plan_head_before: fac15c547dde2abe49552d5c75fee2e87a82ddd0
plan_head_after: a5750507228abc26f43a1fcaf6dfe641f42c98c0

tech-stack:
  added: []
  patterns:
    - "every health signal is compared with the change it judges: scan > install (or new boot) + 5 min, heartbeat > due time with a moved boot_time, service block > change + 120 s"
    - "a restart is proven by a stored baseline (boot_time, last heartbeat, sent and due times) written when the instruction is queued"
    - "not reached = not online at any controller tick of the ring's install window occurrence, judged when that occurrence ends"

key-files:
  created:
    - backend/autonomous_ops/rollout/reboots.py
    - backend/autonomous_ops/rollout/signals.py
    - backend/tests/test_patch_rollout_boot.py
    - backend/tests/test_patch_rollout_health.py
  modified:
    - backend/autonomous_ops/rollout/health.py
    - backend/autonomous_ops/rollout/controller.py
    - backend/autonomous_ops/rollout/dispatcher.py
    - backend/tests/test_patch_rollout_tracer.py

key-decisions:
  - "The Reboot line is raised as soon as the ring's installs have settled, with no window check (D-08 lets a person approve at any time; the approved row is sent by dispatch_approved when a window is open). Install cards stay window-only as 84-03 decided."
  - "The restart time that starts the soak and the 'newer than' tests is max(new boot_time, scheduledRestartAt) stored as newBootAt; a boot can never count as earlier than it was due, which also covers a host clock running behind."
  - "A fresh scan that still lists the installed patch is a failure of the computer (False), not no data; the canary halts canary_failed and a later ring counts it in the failure share. The 84-01 tracer test that expected no_data:inventory was updated."
  - "A computer that needs a restart is judged on inventory and services only after its new boot (newBootAt), so a Windows update that stays listed until the restart does not fail it early."
  - "Services with a service_state token but a tenant without remediation_executor: the agent is never sent the watched list, so no block arrives and the ring halts no_data:services (fail closed, as the research says). service_failures is read for a no-token host only when remediation_executor is ticked."
  - "An unreadable watched-services list is no data for services, not a pass."

patterns-established:
  - "ring_verdict stays pure and takes the operating systems the canary needs as an argument"
  - "Overdue restarts are detected in reboots.settle (every tick, also for a halted rollout) and the controller halts the running rollout with no_new_boot naming the computer"

coverage:
  - id: D1
    description: "Only computers whose result says a restart is needed get a Reboot row (reboot_host, 300 s, the fixed message), one per computer, never twice, and the ring waits for approval before any soak"
    requirement: PTCH-02
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_boot.py#test_only_the_computer_whose_result_says_a_restart_is_needed_gets_a_reboot_row"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_boot.py#test_a_second_tick_raises_no_second_reboot_row"
        status: pass
    human_judgment: false
  - id: D2
    description: "An approved restart is sent once inside the window and stores dispatch time, due time (+300 s), boot baseline and last heartbeat; a new boot starts the soak from the restart"
    requirement: PTCH-02
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_boot.py#test_an_approved_restart_is_sent_once_with_the_warning_and_stores_the_boot_baseline"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_boot.py#test_a_computer_back_on_a_new_boot_is_healthy_and_the_soak_starts_from_the_restart"
        status: pass
    human_judgment: false
  - id: D3
    description: "A heartbeat from before the restart or an unmoved boot_time is never the new boot; no new boot 30 minutes after the due time halts the ring with no_new_boot naming the computer; an undelivered restart is asked for again"
    requirement: PTCH-02
    verification:
      - kind: unit
        ref: "backend/tests/test_patch_rollout_boot.py#test_a_heartbeat_sent_before_the_restart_was_due_is_never_the_new_boot"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_boot.py#test_a_heartbeat_from_before_the_restart_is_never_the_new_boot_and_the_ring_halts_after_thirty_minutes"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_boot.py#test_a_restart_the_computer_never_received_is_asked_for_again_not_taken_for_a_missing_boot"
        status: pass
    human_judgment: false
  - id: D4
    description: "Inventory, heartbeat and services are read only from data newer than the change; a stopped or failed watched service or a still-listed patch fails the computer; a missing or stale signal is no data; Not checked and agent-only never pass or halt"
    requirement: PTCH-02
    verification:
      - kind: unit
        ref: "backend/tests/test_patch_rollout_health.py#test_inventory_needs_a_scan_more_than_five_minutes_after_the_install"
        status: pass
      - kind: unit
        ref: "backend/tests/test_patch_rollout_health.py#test_a_host_that_reports_service_state_must_show_every_watched_service_running_after_the_new_boot"
        status: pass
      - kind: unit
        ref: "backend/tests/test_patch_rollout_health.py#test_a_host_without_the_service_state_token_is_not_checked_unless_it_reports_a_watched_failure"
        status: pass
    human_judgment: false
  - id: D5
    description: "The failure share is judged in whole numbers at every threshold (9/1 halts, 10/1 does not, 10/2 and 11/2 halt), a canary halts on one failure, order never changes the verdict, and 0 reported computers keep the ring waiting"
    requirement: PTCH-03
    verification:
      - kind: unit
        ref: "backend/tests/test_patch_rollout_health.py#test_the_failure_share_is_judged_at_every_threshold_with_minimum_10_and_limit_10_percent"
        status: pass
      - kind: unit
        ref: "backend/tests/test_patch_rollout_health.py#test_the_share_is_compared_in_whole_numbers_so_no_rounding_decides_a_halt"
        status: pass
      - kind: unit
        ref: "backend/tests/test_patch_rollout_health.py#test_the_verdict_and_the_named_computer_do_not_depend_on_the_order_of_the_list"
        status: pass
    human_judgment: false
  - id: D6
    description: "A computer offline for the whole install window is Not reached, left out of both counts, and the canary waits for the next window when an operating system has no installed computer, trying the not-reached computer again"
    requirement: PTCH-01
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_health.py#test_a_computer_offline_for_the_whole_window_is_not_reached_and_the_canary_is_judged_without_it"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_health.py#test_the_canary_waits_for_the_next_window_when_an_operating_system_was_never_reached"
        status: pass
    human_judgment: false

duration: 35min
completed: 2026-11-06
---

# Phase 84 Plan 08: Health Gate Summary

**The rollout health gate is real: restarts are approved per ring and proven by a stored boot baseline, every health signal is read from data newer than the change it judges, a missing signal halts the ring, and the failure share is compared in whole numbers at every threshold.**

## Performance

- **Duration:** about 35 min (start time was not recorded; estimated from the first commands)
- **Tasks:** 3 (all `tdd="true"`)
- **Files:** 4 created, 4 modified (backend only; no UI, no agent change)

## Accomplishments

- **Restarts (Task 1).** After a ring's installs settle, `reboots.raise_reboot_line` raises one `reboot_host` approval row (300 s, "Restarting in 5 minutes for updates") for each installed computer whose result needs a restart, and only for those. Approving the line sends each row once inside the window; `dispatcher.send` then calls `reboots.record_baseline` (dispatch time, due time, boot_time, last heartbeat) and the computer reads restarting. `is_new_boot` needs a heartbeat after the due time, a boot_time more than 120 s past the baseline and not earlier than dispatch minus 120 s; an agent with no readable boot_time gives no answer. `reboots.settle` runs every tick (also on a halted rollout): a new boot makes the computer healthy and starts the soak from the restart, an instruction that was refused or cancelled fails its row `rollout_not_delivered` and raises a new card (at most 3 tries), and 30 minutes after the due time without a new boot marks the computer failed `no_new_boot`; the controller halts the ring naming it.
- **Signals (Task 2).** `signals.host_signals` returns install, inventory, heartbeat and services plus `failed`, `reported`, `os`, `hostname`. Inventory needs a scan more than 5 minutes after the change and fails when the patch is still listed; heartbeat is after the install report, or the new boot for a restarted computer; services are `agent_only` with no watched list, True/False/None from the `service_state` block for a token host, and `not_checked` for a host without the token unless `service_failures` names a watched service.
- **Gate (Tasks 2 and 3).** `ring_verdict` names the first failing computer by (hostname casefold, agent id), reports `no_reports` while no computer has reported, `canary_os` while an operating system of the rollout has no installed computer, and halts on `no_data:<signal>` after the soak. The ring stores `health` rows (signal, state, k, n, notChecked) for the views. A computer offline at every tick of its ring's window occurrence becomes `not_reached` when the occurrence ends; the canary tries it again in a later window while its operating system is uncovered.

## Task Commits

1. Task 1 RED: `8e9da0796` test(84-08) failing tests for the reboot line, baseline and new-boot check
2. Task 1 GREEN: `186bd6c63` feat(84-08) restarts per ring with a boot baseline and a new-boot check
3. Task 2 RED: `28fc3fc70` test(84-08) failing tests for the health signals and never-reached computers
4. Task 2 GREEN: `915a9dbb9` feat(84-08) signals from fresh data, watched services, not reached
5. Task 3: `a57505072` test(84-08) pin the failure-share and missing-data edges

## TDD Gate Compliance

- Task 1 and Task 2: RED commits precede GREEN commits. RED was a skeleton module (functions answering "nothing happened" / "no data") plus the tests, so every RED failure was an assertion on the planned behavior (12 of 13 and 12 of 15 tests failed on assertions; the 4 that passed were guards that the skeleton's neutral answer satisfies). The `gsd_run check tdd-red-evidence` classifier was not run: pytest's console output is not one of its supported report formats and this plan is `type: execute`, not `type: tdd`.
- Task 3: the table tests passed as soon as they were written because Task 2 already implemented `ring_verdict` to the plan's truths. A mutation check (float comparison instead of integers) made two of them fail, so they do constrain the code. There is no separate RED commit for Task 3.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] The 84-01 tracer test pinned a still-listed patch as `no_data:inventory`**
- **Found during:** Task 2
- **Issue:** The plan makes a scan that still lists the patch False (a failure of the computer), but `test_a_fresh_scan_that_still_lists_the_patch_does_not_pass` expected the old "no data" halt.
- **Fix:** The test now expects the canary to halt `canary_failed` naming a1 (renamed `..._fails_the_canary`). The "scan not newer than the install" test still expects `no_data:inventory`.
- **Files modified:** backend/tests/test_patch_rollout_tracer.py
- **Commit:** 915a9dbb9

**2. [Rule 3 - Blocking] `record_baseline` also sets the host state to restarting**
- **Found during:** Task 1
- **Issue:** The plan has the dispatcher set the state separately; two writes could leave a restart queued with the host not marked restarting between them.
- **Fix:** One write in `reboots.record_baseline` stores the baseline and `state: restarting`; the dispatcher only calls it.
- **Files modified:** backend/autonomous_ops/rollout/reboots.py, dispatcher.py
- **Commit:** 186bd6c63

**3. [Rule 3 - Blocking] `reboots` imports `lines` inside `raise_reboot_line`**
- **Found during:** Task 1
- **Issue:** `lines` imports `dispatcher`, which now imports `reboots`; a module-level import would be circular.
- **Fix:** function-level import with a comment.
- **Commit:** 186bd6c63

**Total deviations:** 3 auto-fixed (1 bug-expectation, 2 blocking). **Impact:** none on behavior beyond the plan; `host_signals` keeps the plan's async signature and reads the agent itself when none is passed.

## Decisions and Edges Worth Knowing

- A computer that is not reached is only detected while it still needs its first decision. An install card that was already approved and then could not be delivered because the computer went offline stays approved until it returns (the ring waits for it). Not handled here.
- A reboot row stuck `dispatching` with no baseline stored (a database error between queueing and recording) is left alone, not failed; the ring then waits. This should be rare.
- The default watched-service list is empty, so out of the box every host reads `agent_only` ("Only the agent service is checked").

## Known Stubs

None.

## Threat Flags

None. The plan's threats are mitigated: T-84-26 (baseline stored at dispatch, new boot needs a later heartbeat and a moved boot_time), T-84-27 (only a scan more than 5 minutes after the change counts), T-84-28 (no token means Not checked, a token host with no fresh block is no data and halts).

## Issues Encountered

None.

## Verification

- `backend/tests/test_patch_rollout_boot.py` 13 passed; `test_patch_rollout_health.py` 45 passed (28 test functions, parametrised); with the other `test_patch_rollout_*`, `test_autonomous_ops_copy`, `_structural`, `_reconciler`, `_dispatch_binding` and `_approvals` files: 412 passed on a private mongod (port 27998, stopped afterwards).
- Acceptance: `def is_new_boot|record_baseline|raise_reboot_line` count 3; `def host_signals` count 1; `not_checked` in signals.py 3; `def test_` in the health tests 28 (at least 15); the overdue test asserts the halt text names `host-a1`.

## Next Phase Readiness

Ready for 84-09 and 84-10 (views read the ring `health` rows and the host fields `rebootNeeded`, `newBootAt`, `notReachedWindow`). The agent still has to ship `service_state` (84-11); until then every computer with a watched list reads Not checked.

## Self-Check: PASSED
