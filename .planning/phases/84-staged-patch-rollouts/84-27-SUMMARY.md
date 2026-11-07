---
phase: 84-staged-patch-rollouts
plan: 27
subsystem: autonomous-ops
status: complete
tags: [patch-rollout, settle, in-flight, timeouts, revert, gap-closure, python]

requires:
  - phase: 84-staged-patch-rollouts
    provides: 84-20 settle (stop rule), 84-13 revert, 84-23 held canary lines and track_line
provides:
  - inflight.instruction_outcome(task, now, dispatched): pending | not_delivered | failed | no_result | done for one instruction
  - RESULT_DEADLINE (6 h) and DISPATCH_CLAIM_BOUND (10 min), inflight.close_job(...), inflight.load_instruction(...)
  - reasonCode rollout_no_result (REASON_TEXT, ignored by the circuit breaker, host failureCode)
  - not-reverted code no_answer ("the computer did not answer")
  - host waitReason not_approved ("Not approved. Nothing was installed.")
  - settle.recover_unsent: a row dispatching with no instruction past the bound is failed and retried
affects: [84-28, 84-29]

requirements-completed: [PTCH-02, PTCH-04, PTCH-06, PTCH-07]

actuals:
  tokens: 14300
  tasks: 3
  commits: 6
commits: 6
plan_head_before: ca2b7011e44235933c2ef5193ac5831ef58f7bd0
plan_head_after: 6992b583f2a87dbc8bf3c76bb9d4bf2063b5ced3

tech-stack:
  added: []
  patterns:
    - "one outcome reader for every instruction a rollout sends (install, line install, revert); callers never compare raw statuses"
    - "a step that cannot be answered ends in a named state with a reason, and its patch job is closed so nothing reads busy"

key-files:
  created:
    - backend/autonomous_ops/rollout/inflight.py
    - backend/tests/test_patch_rollout_gap_inflight.py
  modified:
    - backend/autonomous_ops/rollout/settle.py
    - backend/autonomous_ops/rollout/revert.py
    - backend/autonomous_ops/rollout/dispatcher.py
    - backend/autonomous_ops/rollout/installs.py
    - backend/autonomous_ops/rollout/lifecycle.py
    - backend/autonomous_ops/rollout/messages.py
    - backend/autonomous_ops/rollout/views.py
    - backend/autonomous_ops/messages.py
    - backend/autonomous_ops/ledger.py
    - backend/tests/test_patch_rollout_gap_lines.py
    - backend/tests/test_patch_rollout_messages.py

key-decisions:
  - "RESULT_DEADLINE = 6 hours after the instruction was delivered (Linux installs run up to 30 minutes per package). DISPATCH_CLAIM_BOUND = 10 minutes. Both are module constants in rollout/inflight.py, read with an injected now. Reversible: constants only."
  - "A pending or sent instruction with an expiresAt is only ever judged by that expiry (not_delivered once past, pending before); the 6 hour deadline applies to delivered, accepted, success and expiry-less instructions (reverts have no expiry)."
  - "An expired or refused install is a failure of the delivery, not of the computer: it is retried (MAX_ATTEMPTS), never halts the ring, and is transparent to the breaker. FAILURE and 6 hours of silence fail the computer, and the ring halts on it."
  - "A refused or cancelled revert keeps its not_delivered reason (existing behaviour); a revert answered FAILURE, expired, or silent past the deadline reads no_answer."
  - "A denied or expired (outside a stop) approval row never lets the computer fall through to installed: it stays waiting with waitReason not_approved. The 84-20 rule that an Install row expired inside a stop is offered again is untouched."

coverage:
  - id: D1
    description: "An install the agent answers FAILURE, or never answers within RESULT_DEADLINE, fails the computer with a reason and the ring halts; an expired unread instruction is retried and never fails the computer; rollout_no_result is transparent to the circuit breaker"
    requirement: PTCH-06
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_gap_inflight.py#test_a_canary_install_the_agent_answers_failure_fails_the_computer_and_halts_the_ring"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_gap_inflight.py#test_a_canary_install_nobody_answers_for_six_hours_fails_the_computer_and_not_a_second_sooner"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_gap_inflight.py#test_an_install_instruction_that_expired_unread_is_not_delivered_and_the_computer_is_tried_again"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_gap_inflight.py#test_an_install_nobody_answered_does_not_count_toward_the_circuit_breaker"
        status: pass
    human_judgment: false
  - id: D2
    description: "A revert answered FAILURE, expired, or silent past the deadline ends as Not reverted: the computer did not answer, and Resume is no longer blocked"
    requirement: PTCH-04
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_gap_inflight.py#test_a_revert_the_agent_fails_or_never_answers_reads_not_reverted_and_resume_is_unblocked"
        status: pass
    human_judgment: false
  - id: D3
    description: "A computer whose Install line was denied or expired never reads installed; one that expired inside a stop is still offered again"
    requirement: PTCH-02
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_gap_inflight.py#test_a_computer_whose_install_line_was_denied_is_never_shown_installed"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_gap_inflight.py#test_a_computer_whose_install_line_expired_unanswered_is_never_shown_installed"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_gap_inflight.py#test_an_install_line_that_expired_inside_a_stop_is_still_offered_again"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_gap_lines.py#test_denying_the_held_canary_line_halts_the_rollout_with_install_denied"
        status: pass
    human_judgment: false
  - id: D4
    description: "A row left dispatching with no instruction, or whose send raised, ends failed rollout_not_delivered and the computer is decided again; every abandoned install closes its job so the computer never reads busy"
    requirement: PTCH-06
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_gap_inflight.py#test_a_dispatching_row_with_no_instruction_is_recovered_and_the_computer_is_decided_again"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_gap_inflight.py#test_a_send_that_raises_ends_the_row_and_the_computer_waits_to_be_tried_again"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_gap_inflight.py#test_an_expired_canary_instruction_closes_its_job_so_the_computer_is_not_busy"
        status: pass
    human_judgment: false
---

# Phase 84 Plan 27: In-flight bounds Summary

**A rollout install the agent answers FAILURE or never answers within 6 hours now fails its computer so the ring halts, a revert always ends, a denied computer is never called installed, and a dispatching row with no instruction is recovered with its job closed.**

**Duration:** about 40 min | **Tasks:** 3 | **Files:** 2 created, 11 modified

## Accomplishments

- **WR-03 (in flight).** New `rollout/inflight.py` holds the one outcome reader. `settle` (automatic row and Install line rows) and `revert` use it: `FAILURE`/`error` fails the computer (`rollout_install_failed`, the agent's own words on the host), an instruction still pending or sent after its own `expiresAt` is not delivered (row `rollout_not_delivered`, computer back to waiting, retried up to `MAX_ATTEMPTS`), and a delivered install with no result 6 hours after delivery fails the computer with the new `rollout_no_result` (host `failureCode`, "The computer did not answer within 6 hours."). The boundary is exact: 1 s before stays installing, 1 s after fails. `rollout_no_result` is in `BREAKER_IGNORED`.
- **WR-03 (revert).** A reverting computer whose revert is answered FAILURE, expired, or silent past the deadline leaves `reverting` as `not_reverted` with the new code `no_answer` ("Not reverted: the computer did not answer. The patch is still installed."). The halt summary says it in words and `lifecycle.resume` no longer raises `RevertRunning` for it. A refused revert keeps its `not_delivered` reason.
- **WR-04.** A denied or expired (outside a stop) Install row sets `Progress.closed`; with nothing else open the computer stays `waiting` with `waitReason: not_approved` ("Not approved. Nothing was installed.") instead of `installed`, in the same tick as the denial and on every later tick. Covers the canary held line and later rings. Tightened the two 84-23 deny/expiry tests to assert the host state.
- **WR-06.** `settle.recover_unsent` (run first in every settle pass, error-isolated) fails an install row `dispatching` with no resolvable instruction for 10 minutes, closes its job, and resets an automatic row's host through the existing `retry_fields` so the next decision is a new attempt. `dispatcher.send` and `installs._send` now catch an exception from the job insert or `gate.execute`, end the row `rollout_not_delivered` (not the approvals module's `dispatch_failed`), and log once.
- **WR-02.** `inflight.close_job` moves an In Progress job to Failed with one error status line. Called on the automatic and line not-delivered paths, the failed and no-result paths, the WR-06 recovery, both send-exception paths, the dispatcher's refused and stop-cancelled paths, `installs._fail_undelivered`, the revert no-answer path and `lifecycle._end_unfetched`. `start._busy_agents` no longer lists the computer afterwards.

## TDD record

- **RED** (`c6cc296d7`, `495178f09`, `e9d3a942a`): each failed on the planned assertion for the intended reason (host still `installing`; host `installed` after a denial; revert host still `reverting`; row still `dispatching` or ended `dispatch_failed`). No load, fixture or syntax fault. Tests that passed at RED were guards on rules that were already true or came from Task 1: the stop-expired Install line is still offered again (84-20 rule), a row younger than the claim bound is left alone, and an expired canary instruction closes its job (its close_job call landed with the Task 1 not-delivered fix, which already edited those lines).
- **GREEN** (`910b6d309`, `c1e95941c`, `6992b583f`): 15/15 in `test_patch_rollout_gap_inflight.py`; the full `test_patch_rollout_*.py` plus `test_autonomous_ops_ledger.py` and `test_autonomous_ops_verify.py` pass (452 passed) on a private mongod on port 27998 (stopped afterwards). `ruff --select F` is clean on the rollout package and the new test file.
- No REFACTOR commit.

## Commits

| Hash | Message |
|------|---------|
| c6cc296d7 | test(84-27): add failing tests for failed, silent and expired canary installs |
| 910b6d309 | feat(84-27): an install the agent answers FAILURE or never answers ends, and an expired one is retried |
| 495178f09 | test(84-27): add failing tests for a silent revert and a denied computer shown installed |
| c1e95941c | feat(84-27): a revert always ends and a denied computer is never shown installed |
| e9d3a942a | test(84-27): add failing tests for stuck dispatching rows and sends that raise |
| 6992b583f | feat(84-27): a dispatching row with no instruction is recovered and abandoned jobs are closed |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] REASON_TEXT lives in `autonomous_ops/messages.py`, not `rollout/messages.py`**
- **Found during:** Task 1
- **Issue:** the plan listed `rollout/messages.py` for the `rollout_no_result` sentence; every `reasonCode` sentence (`ledger` rows read `messages.REASON_TEXT`) is in the parent module. The acceptance grep for `rollout_no_result` in `rollout/messages.py` therefore does not match; it matches `autonomous_ops/messages.py` and `ledger.py`.
- **Fix:** added the sentence to `autonomous_ops/messages.py`.
- **Commit:** 910b6d309

**2. [Rule 3 - Blocking] A stored message set was pinned by a test**
- **Found during:** Task 2
- **Issue:** `test_patch_rollout_messages.py` pinned the Not reverted codes to the original three.
- **Fix:** the expected set now includes `no_answer`, plus an assertion of its sentence.
- **Commit:** c1e95941c

**3. [Rule 2 - Missing critical] A halt left the cancelled install's job In Progress**
- **Found during:** Task 3
- **Issue:** `lifecycle._end_unfetched` fails a pending dispatching row on a halt, leaving its job In Progress and the computer busy. The plan said to change it only if no other change was needed there.
- **Fix:** it now takes `now` (one caller) and calls `close_job`.
- **Commit:** 6992b583f

**4. [Plan wording] Test count and a helper placement**
- The file has 15 tests, not 10 (parametrized revert and send variants, a boundary guard, and the denied/expired split). The outcome reader and `close_job` went into the new `rollout/inflight.py` (settle.py would have passed 500 lines only marginally, but revert, dispatcher and installs also need them without a circular import).

**Total deviations:** 3 auto-fixed, 1 wording. **Impact:** none on scope.

## Left for review

- **Reboot rows.** `reboots.settle` reads instruction status itself (its own copy of the not-delivered tuple). `recover_unsent` only covers install rows; a reboot row stuck `dispatching` with no instruction is ended only when `dispatcher.send` itself raises (it now ends any claimed row), not by a timeout. Not changed because the reboot settle does not read the same fields.
- **Resume after a denial.** A computer left `waiting / not_approved` by a denial stays so after Resume until a new line is raised; the ring does not pass on a denied computer any more. Plan 84-28's cancel/resume work should check this against "Resume" semantics.
- **Windows revert wording.** The `no_answer` text is the same for Windows and Linux computers.

## Known Stubs

None.

## Threat Flags

None. No new endpoint, auth path or schema; T-84-74, T-84-75 and T-84-76 mitigated as planned (instruction status and result still come from the existing agent routes, only read here).

## Self-Check: PASSED

- inflight.py, test_patch_rollout_gap_inflight.py and all modified files present; every changed file under 500 lines (views.py 444, lifecycle.py 388).
- Commits c6cc296d7, 910b6d309, 495178f09, c1e95941c, e9d3a942a, 6992b583f are ancestors of HEAD.
- Acceptance greps: `RESULT_DEADLINE` and `DISPATCH_CLAIM_BOUND` defined in `rollout/inflight.py` and used in `instruction_outcome` and `settle.recover_unsent`; `rollout_no_result` in `ledger.py` and `autonomous_ops/messages.py`; `no_answer` in `rollout/messages.py` and `revert.py`; `not_approved` in `settle.py`; `close_job` has 9 call sites outside its definition.
- Private mongod on port 27998 stopped.
