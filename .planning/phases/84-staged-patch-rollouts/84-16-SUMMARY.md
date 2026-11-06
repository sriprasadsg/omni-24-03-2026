---
phase: 84-staged-patch-rollouts
plan: 16
subsystem: autonomous-ops
status: complete
tags: [patch-rollout, resume, cancel, not-reached, activity, mongodb, python]

requires:
  - phase: 84-staged-patch-rollouts
    provides: 84-03 halt and lines; 84-08 reboots and health; 84-09 views and routes; 84-13 revert
provides:
  - lifecycle.resume and lifecycle.cancel (halted rollouts only), errors RolloutNotFound, NotHalted, RevertRunning, ReasonRequired
  - POST /api/patch-rollouts/{id}/resume and /cancel (ResumeBody), manage:patches in a signed-in session
  - complete() that keeps never-reached computers for 7 days (notReached, closesAt), offer_returning, release_reached, close_if_due (closedAt, neverReachedCount)
  - controller tail pass over completed unclosed rollouts and cancelled rollouts with a running revert
  - Activity Why and Result texts on rollout rows, all from messages.ACTIVITY
affects: [84-18, 84-19, 84-22]

requirements-completed: [PTCH-01, PTCH-04, PTCH-07]

actuals:
  tokens: 26500
  tasks: 3
  commits: 5
commits: 5
plan_head_before: cd9a24320c03f8816e8ee69009c60c283a833b96
plan_head_after: db3870beb5a414c83c6edc93e5bd98f2763d34eb

tech-stack:
  added: []
  patterns:
    - "Resume judges the halted ring with the controller's own signals.ring_signals + health.ring_verdict; only a green verdict continues, one compare-and-set flips status, passes the ring and moves currentRing"
    - "a change a person makes to a safeguard (resume, cancel) is flipped first, then recorded; if the control row cannot be written the flip is undone"
    - "a row keeps its Why in reasonText and gets its Result in activityResult; response_views.row_extras shows it as resultText for the rollout dispatcher"

key-files:
  created:
    - backend/tests/test_patch_rollout_lifecycle.py
    - backend/tests/test_patch_rollout_activity.py
  modified:
    - backend/autonomous_ops/rollout/lifecycle.py
    - backend/autonomous_ops/rollout/controller.py
    - backend/autonomous_ops/rollout/store.py
    - backend/autonomous_ops/rollout/health.py
    - backend/autonomous_ops/rollout/signals.py
    - backend/autonomous_ops/rollout/messages.py
    - backend/autonomous_ops/rollout/lines.py
    - backend/autonomous_ops/rollout/dispatcher.py
    - backend/autonomous_ops/rollout/installs.py
    - backend/autonomous_ops/rollout/settle.py
    - backend/autonomous_ops/rollout/revert.py
    - backend/autonomous_ops/rollout/reboots.py
    - backend/autonomous_ops/messages.py
    - backend/autonomous_ops/ledger.py
    - backend/autonomous_ops/response_views.py
    - backend/patch_rollout_endpoints.py

key-decisions:
  - "OQ4 (planner decision, kept): a rollout is Completed as soon as every ring passed. Computers it never reached stay in notReached with closesAt = completedAt + NOT_REACHED_GRACE (7 days, research A11) and keep their claims. A returning one is offered the install as an approval line in the next open window, never automatically. At closesAt the rollout closes (status stays completed, closedAt and neverReachedCount are set), the remaining claims are released and open rows expire."
  - "Resume continues only on verdict green and no pending restart in the halted ring, judged on current data from the same signals the controller uses. A waiting verdict (soak not over, no reports) is not green and keeps the old halt reason; a halt verdict stores the new reason. Nothing removes, excludes or counts a failed computer as passed (PROH-84-07)."
  - "Both Resume outcomes write one control row and audit event naming the person (rollout_resumed, or rollout_resume_checked for a kept-halted check); Cancel writes rollout_cancelled."
  - "Cancel marks rings that did not pass as cancelled, releases every claim, expires open rows (rollout_closed) and sets revertOpen when a computer is still being reverted; the controller keeps settling that revert and then drops the flag."
  - "An Activity row keeps its Why in reasonText and gets its Result in a separate activityResult field, so the Why and Result columns of UI-SPEC section 7 both read right."

patterns-established:
  - "tail rollouts: store.TAIL_FILTER names the finished rollouts the controller still tends (completed with closesAt and no closedAt, cancelled with revertOpen)"

coverage:
  - id: D1
    description: "Resume continues a halted rollout only through a green health check on current data with a typed reason; a red check keeps it halted with the new reason and leaves the failed computer failed and counted; refused while a revert runs, on a rollout that is not halted, for a missing or over-long reason, for another organization, a viewer or an API key; one control row and one audit event name the person"
    requirement: PTCH-01
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_lifecycle.py#test_resume_on_a_red_check_keeps_the_rollout_halted_with_the_new_reason_and_skips_nothing"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_lifecycle.py#test_resume_on_a_green_check_passes_the_ring_and_goes_on_with_one_record"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_lifecycle.py#test_the_routes_map_each_refusal_to_its_status_and_sentence"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_lifecycle.py#test_a_viewer_and_an_api_key_cannot_resume_or_cancel"
        status: pass
    human_judgment: false
  - id: D2
    description: "Cancel ends a halted rollout: rings that did not pass are cancelled, every claim is released, open rows expire, a running revert is left to finish and is still settled; patched computers keep their patches"
    requirement: PTCH-07
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_lifecycle.py#test_cancel_ends_the_rollout_frees_every_claim_closes_open_rows_and_leaves_a_revert_alone"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_lifecycle.py#test_a_cancelled_rollouts_revert_is_still_settled_by_the_controller"
        status: pass
    human_judgment: false
  - id: D3
    description: "A rollout whose every ring passed is completed; computers it never reached are tracked for 7 days with their claims, offered the install as an approval (never automatically) when they return inside a window, and counted and released when the rollout closes"
    requirement: PTCH-01
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_lifecycle.py#test_the_last_ring_completes_the_rollout_and_keeps_only_the_computer_it_never_reached"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_lifecycle.py#test_a_computer_back_online_in_a_window_is_offered_the_install_as_an_approval_never_automatically"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_lifecycle.py#test_a_computer_that_never_returns_is_counted_and_released_when_the_rollout_closes"
        status: pass
    human_judgment: false
  - id: D4
    description: "Activity rows for rollout installs, reverts and restarts carry the UI-SPEC section 7 Why and Result texts from messages.ACTIVITY, and a computer that could not be put back never reads as reverted"
    requirement: PTCH-04
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_activity.py#test_a_canary_install_says_why_it_ran_and_what_the_agent_confirmed"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_activity.py#test_a_revert_names_the_ring_that_halted_and_what_the_computer_confirmed"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_activity.py#test_a_restart_that_saw_the_new_boot_says_when_the_computer_came_back"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_activity.py#test_the_activity_list_returns_the_why_and_result_of_a_rollout_row"
        status: pass
    human_judgment: false
  - id: D5
    description: "How Resume, Cancel and a returning computer's approval look and feel on the Rollouts tab and in Needs your decision, and a real halt, resume and close on a live organization"
    requirement: PTCH-01
    verification: []
    human_judgment: true
    rationale: "The screens are plans 84-14, 84-17 and 84-18; a live rollout can only be run by the user on the live platform"

duration: 27min
completed: 2026-11-06
---

# Phase 84 Plan 16: Resume, Cancel, Not-Reached Tracking and Activity Texts Summary

**A halted rollout can only be resumed through a green health check on current data (with a recorded reason) or cancelled; a finished rollout keeps the computers it never reached for a week, offers them the install as an approval when they return, then closes; and Activity says in plain words what each rollout step did.**

## Performance

- **Duration:** about 27 min (including an 8m50s regression run of 1,445 tests)
- **Tasks:** 3 (all `tdd="true"`)
- **Files:** 2 created, 16 modified (backend only)

## Accomplishments

- **Resume and Cancel (Task 1).** `lifecycle.resume` checks the reason (1 to 500 characters with a non-space), the rollout (404 for another organization), that it is halted, and that no computer is still reverting (R10). It then judges the halted ring with `signals.ring_signals` and `health.ring_verdict` (the controller's own code, now shared) and also requires that no restart is pending. Green: one compare-and-set moves the rollout from halted to running, marks the ring passed and moves `currentRing` (the last ring completes the rollout). Red: the rollout stays halted, the ring's health rows and failed/reported counts are refreshed, a failing verdict stores the new `haltReason`, and a check that is only waiting for data keeps the old reason. No failed computer is touched. `lifecycle.cancel` ends a halted rollout (rings that did not pass become cancelled, claims released, open rows expire `rollout_closed`). Both write a control row and an audit event naming the person; if that record fails the flip is undone. The two routes need `manage:patches` and a signed-in session; errors are 404, 409 (`not_halted`, `revert_running`) and 422 (`reason_required`) with the `messages.API_DETAIL` sentences. The response is `{status: resumed | still_halted | cancelled, reason, ring}`.
- **Completion, not-reached computers and closing (Task 2).** `complete` keeps the claims of `not_reached` computers and records `notReached` and `closesAt` (+7 days). The controller now also tends finished rollouts (`store.TAIL_FILTER`): it settles returning computers' installs, releases claims of those reached after all, offers a computer that is online inside an open window the install as an approval line (never automatic, never during a stop or when Off), sends approved ones, and at `closesAt` closes the rollout (`closedAt`, `neverReachedCount`, claims released, open rows expired). A closed or cancelled rollout with no running revert is never visited again. `lines._running` and `dispatcher.host_problem` now allow the install line on a completed, unclosed rollout.
- **Activity texts (Task 3).** The canary row is created with the Why `{rollout}: canary ring, reversible patch ({patch}).` and gets the Result `Installed {patch}. Verified: it is no longer pending.` or `The computer did not confirm the install, so this is marked failed.`; a revert row gets `{ring} halted: {reason}.` and `Reverted ... Verified: the earlier version is installed.`, `Uninstalled {KB}. Verified: it is no longer listed.` or `Not reverted: {reason}. The patch is still installed.`; a restart row gets `{rollout}: {ring} needs a restart.` and `Restarted. Warned 5 minutes before. Back online at {HH:MM}.` in the organization's zone; a first-ring install waiting for a person says `Waiting for your approval.`. All sentences are from `messages.ACTIVITY`.

## Task Commits

1. Task 1 RED: `9b26b3423` test(84-16) failing tests for resume and cancel of a halted rollout
2. Task 1 GREEN: `b8e142cdc` feat(84-16) resume and cancel a halted rollout through the health gate
3. Task 2 GREEN: `f1d66ab3e` feat(84-16) a finished rollout tracks computers it never reached for a week
4. Task 3 RED: `c1927e5ec` test(84-16) failing tests for the Activity texts
5. Task 3 GREEN: `db3870beb` feat(84-16) Activity rows say what each rollout install, revert and restart did

## TDD Gate Compliance

Tasks 1 and 3 have a RED commit that fails for the right reason before the GREEN commit (AttributeError for `lifecycle.resume`; wrong or missing texts for Activity). Task 2 has no separate RED commit: its tests were written after the shared code (`complete`, the controller tail, `close_if_due`) had landed in the Task 1 GREEN commit, because Cancel's running revert needs the same controller tail. When the Task 2 tests were first run, seven of eight passed and the one failure (a returning computer's approval refused on a completed rollout) was the real gap, closed in `f1d66ab3e`. `gsd_run check tdd-red-evidence` was not run (this plan is `type: execute`; pytest output is not one of its formats).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical] The Result text is kept in its own field, not in `reasonText`**
- **Found during:** Task 3
- **Issue:** The plan has the success and failure transitions overwrite `reasonText` with the Result. The row's `reasonText` is the Why column of UI-SPEC section 7, so the canary row would have lost its Why the moment the agent answered (and the Result column would have read the generic "Done.").
- **Fix:** the row keeps its Why in `reasonText` and gets the Result in `activityResult` (new `ledger.set_display` for results that arrive after the row changed state, such as a revert); `response_views.row_extras` returns it as `resultText` for the rollout dispatcher. Also the generic reason text is no longer written over the Why on an executed or failed install row; the reason code is unchanged, so the breaker is unaffected.
- **Files modified:** backend/autonomous_ops/ledger.py, backend/autonomous_ops/response_views.py (not in the plan's file list), settle.py, revert.py, reboots.py, installs.py
- **Commit:** db3870beb

**2. [Rule 3 - Blocking] A returning computer's approval could not be approved or sent**
- **Found during:** Task 2
- **Issue:** `lines._running` and `dispatcher.host_problem` accepted only a running rollout, so the install line raised for a computer that came back after the rollout completed was a dead card.
- **Fix:** the install line is accepted on a completed rollout that is not closed yet (`closedAt` unset); a closed rollout has no claims, so `host_problem` still answers `claim_released`.
- **Files modified:** backend/autonomous_ops/rollout/lines.py, backend/autonomous_ops/rollout/dispatcher.py (not in the plan's file list)
- **Commit:** f1d66ab3e

**3. [Rule 3 - Blocking] The controller never visited a cancelled rollout, so its running revert would stay "Reverting" forever**
- **Found during:** Task 1
- **Fix:** Cancel sets `revertOpen` when a computer is still being reverted; `store.TAIL_FILTER` and `controller._tail` keep settling that revert (no new lines, no new reverts) and then clear the flag.
- **Files modified:** store.py, controller.py, lifecycle.py
- **Commit:** b8e142cdc

**4. [Rule 3 - Blocking] The control events had no labels, and the ring check lived inside the controller**
- **Found during:** Task 1
- **Fix:** `rollout_resumed`, `rollout_resume_checked` and `rollout_cancelled` added to `CONTROL_LABELS` (autonomous_ops/messages.py); the signal gathering, failed/reported counts, required operating systems and halt facts moved out of `controller._check` into `signals.ring_signals`, `health.health_counts`, `health.required_os` and `lifecycle.halt_facts` so Resume judges a ring with exactly the controller's code.
- **Commit:** b8e142cdc

**Total deviations:** 4 auto-fixed (1 missing critical, 3 blocking). **Impact:** no change to the plan's intent; the one visible difference is where the Result sentence lives on the ledger row.

## Known Gaps and Edges

- **A ring halted by a denied or expired approval cannot be resumed.** Nothing installed in that ring, so its check has no data and never turns green (no skipping is allowed); the only way out is Cancel. A later plan could let Resume re-raise the approval line; it would be a new rule, not a gate-green resume.
- **A resumed ring whose computers were already reverted reads red** (the patch is pending again), so Resume only succeeds where the ring still carries its install or its data catches up. This is the safe reading of D-16 ("continues only if green", no skipping).
- 84-13 edges are unchanged: a refused or overdue revert restart is not asked for again; a computer that never settles from installing or restarting is never reverted.
- **A returning computer that needs a restart after its late install** is not asked to restart (the rollout is already completed and has no ring state machine); `rebootNeeded` stays on its card.
- **An install sent to a returning computer in the last minutes before `closesAt`** is not settled after the rollout closes (its host reads installing); the claim is released at close.
- **Not wired:** the "outside window" and "never-touch" Activity rows of UI-SPEC section 7 (`outside_window_*`, `never_touch_*`) and the Simulation wording have no code path in the rollout today, so they stay as messages only. The later-ring (non-first-ring) approval row keeps the card's Why.
- `test_patch_rollout_claims.py::test_two_starts_at_once...` (handoff note): the claim release in Cancel is the same `store.release` call; the claims, tracer, lines, dispatcher, controller and lifecycle files were run three times in a row, 116 passed each time, and the full 1,445-test run passed.
- A live halt, resume, cancel and close on a real organization is a user check (coverage item D5).

## Known Stubs

None.

## Threat Flags

None beyond the plan's register. T-84-48 (Resume continues only on a green `ring_verdict` over current data; no skip path exists), T-84-49 (control row and audit event with actor and reason, flip undone if unrecorded) and T-84-50 (`_require_manage_patches` and `_require_interactive_session` on both routes; viewer and API key refused) are mitigated and tested.

## Issues Encountered

None open.

## Verification

Private mongod on port 27998 (stopped afterwards):
- Task 1 command: `test_patch_rollout_lifecycle.py`, `test_patch_rollout_endpoints.py`, `test_route_auth_baseline.py`: 56 passed, no skips.
- Task 2 command (`lifecycle`, `tracer`, `claims`; plus `lines`, `dispatcher`, `controller`): 116 passed, three runs in a row.
- Task 3 command: `test_patch_rollout_activity.py`, `_revert`, `_tracer`, `test_autonomous_ops_copy.py`: 86 passed.
- Full regression (`test_patch_rollout_*`, `test_patch_deployment_flow`, `test_autonomous_ops_*`, `test_route_auth_baseline`): 1,445 passed in 8m50s.
- Acceptance: `grep -c "def resume\|def cancel"` lifecycle.py 2; `NOT_REACHED_GRACE` 3 in lifecycle.py; `ACTIVITY` in settle.py 4 and revert.py 4; lifecycle.py 386 and patch_rollout_endpoints.py 299 lines; the still-red test asserts the failed host's state, claim, ring and the ring's failed count.

## Next Phase Readiness

84-18 (the Resume and Cancel dialogs) can call `POST /api/patch-rollouts/{id}/resume` with `{reason}` and read `{status, reason, ring}`, and `.../cancel`. The card fields `closesAt`, `neverReachedCount`, `closedText`, `canResume`, `canCancel` are now filled by the server. 84-22 (the background loop) needs nothing new: `controller.tick` already covers the finished-rollout tail.

## Self-Check: PASSED
