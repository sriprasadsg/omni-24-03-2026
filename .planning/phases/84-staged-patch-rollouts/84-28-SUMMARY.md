---
phase: 84-staged-patch-rollouts
plan: 28
subsystem: autonomous-ops
status: complete
tags: [patch-rollout, cancel, lifecycle, controller, gap-closure, python, react]

requires:
  - phase: 84-staged-patch-rollouts
    provides: 84-16/84-18 halted Cancel and Resume, 84-27 RESULT_DEADLINE and inflight.close_job
provides:
  - lifecycle.cancel accepts a running rollout (answer "cancelling"), stamping cancelRequested {by, at}
  - lifecycle.finish_cancel (shared cancel completion for the halted path and the controller)
  - rollout/cancelling.py tick (settle only, then end the cancel)
  - API_DETAIL["cancel_requested"] (409 for Resume and a second Cancel), CANCEL_NOTE_RUNNING, control event rollout_cancel_requested
  - card fields canCancel (running too), cancelNote; Cancel rollout button on a running card
affects: [84-29]

requirements-completed: [PTCH-04, PTCH-06, PTCH-07]

actuals:
  tokens: 9700
  tasks: 2
  commits: 4
commits: 4
plan_head_before: d20332cef70f2a9c42eb45f2d8a650cc34d69931
plan_head_after: f6d8e13f5012eda31d7716ebc1c3b41c46d75e47

tech-stack:
  added: []
  patterns:
    - "a Cancel request is one compare-and-set stamp; the controller then only settles and never decides, verdicts or halts"
    - "halt itself refuses a rollout with cancelRequested, so no caller can reach the halt/revert path while cancelling"

key-files:
  created:
    - backend/autonomous_ops/rollout/cancelling.py
    - backend/tests/test_patch_rollout_cancel_running.py
    - backend/tests/test_patch_rollout_views_cancel.py
    - src/__tests__/PatchRolloutCancelRunning.test.tsx
  modified:
    - backend/autonomous_ops/rollout/lifecycle.py
    - backend/autonomous_ops/rollout/controller.py
    - backend/autonomous_ops/rollout/views.py
    - backend/autonomous_ops/rollout/messages.py
    - backend/autonomous_ops/messages.py
    - backend/patch_rollout_endpoints.py
    - backend/tests/test_patch_rollout_lifecycle.py
    - backend/tests/test_patch_rollout_messages.py
    - backend/tests/test_patch_rollout_views.py
    - services/patchRollouts/types.ts
    - services/patchRollouts/lifecycle.ts
    - components/patchRollouts/RolloutDialogs.tsx
    - components/patchRollouts/RolloutCard.tsx
    - src/__tests__/PatchRolloutDialogs.test.tsx
    - src/__tests__/_patchRolloutFixtures.ts

key-decisions:
  - "KD-84-G3 (corrected, follows locked D-16): Cancel on a running rollout stops new work and reverts nothing. It stamps cancelRequested {by, at} with a compare-and-set on status running, closes open and approved-not-sent rows, ends unfetched instructions, and from then on the controller only settles in-flight installs and restarts. The rollout ends cancelled (claims released, cancelledBy = the requester) once no computer is installing or restarting, and at the latest RESULT_DEADLINE (6 h, 84-27) after the request. Hosts already patched keep their patches; no revert row and no revert_reboot line is ever created. D-14/D-15 reverts follow a failed ring only; the halted-rollout path is unchanged. Reversible: server code plus one additive rollout field."
  - "A computer still in flight at the RESULT_DEADLINE bound ends failed with rollout_no_result (its row and job closed) rather than reading installing on a cancelled rollout. Nothing is reverted."
  - "lifecycle.halt refuses a rollout with cancelRequested (compare-and-set filter), in addition to the controller skipping every halt path: the halt route cannot be reached from the cancelling branch even through a future caller."
  - "Resume and a second Cancel answer 409 with API_DETAIL['cancel_requested']; cancel of a completed or cancelled rollout keeps the existing not_halted 409."

coverage:
  - id: D1
    description: "Cancel of a running rollout closes open and approved rows, ends unfetched instructions, creates no revert or restart line, and one tick afterwards decides, raises and sends nothing"
    requirement: PTCH-04
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_cancel_running.py#test_cancel_of_a_running_rollout_stops_new_work_closes_rows_and_reverts_nothing"
        status: pass
    human_judgment: false
  - id: D2
    description: "The rollout ends cancelled with every claim released and the requester named once the installs settle; at the latest RESULT_DEADLINE after the request, with no halt and no revert even when a failure settles meanwhile"
    requirement: PTCH-07
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_cancel_running.py#test_the_rollout_ends_cancelled_when_the_installs_settle_and_every_patch_stays"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_cancel_running.py#test_an_install_nobody_answers_ends_the_cancel_without_a_halt_or_a_revert"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_cancel_running.py#test_an_install_still_in_flight_does_not_hold_the_cancel_past_the_deadline"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_cancel_running.py#test_a_rollout_with_a_cancel_requested_can_not_be_halted"
        status: pass
    human_judgment: false
  - id: D3
    description: "Resume and a second Cancel answer 409 while cancelling; the cancel route keeps its permission and session guards; the halted Cancel is unchanged"
    requirement: PTCH-06
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_cancel_running.py#test_a_second_cancel_and_a_resume_are_refused_while_the_cancel_settles"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_cancel_running.py#test_the_cancel_route_asks_for_the_manage_permission_and_a_session"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_cancel_running.py#test_cancel_of_a_halted_rollout_still_ends_it_at_once"
        status: pass
    human_judgment: false
  - id: D4
    description: "The server offers Cancel on a running card with the nothing-is-reverted sentence; neither Cancel nor Resume while cancelling; the dialog shows the note and a cancelling answer closes it and reads the card again"
    requirement: PTCH-04
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_views_cancel.py"
        status: pass
      - kind: unit
        ref: "src/__tests__/PatchRolloutCancelRunning.test.tsx"
        status: pass
    human_judgment: true
    rationale: "Whether the running card's Cancel rollout button and the dialog sentence read well in the Spatial Glass UI needs eyes on the published screen; UI is not published (dist-new only)."
---

# Phase 84 Plan 28: Cancel a running rollout Summary

**An operator can now Cancel a running rollout: new work stops at once, nothing is reverted, and the rollout ends cancelled (claims released, requester named) when the installs in progress settle, at the latest 6 hours after the request.**

**Duration:** about 15 min | **Tasks:** 2 | **Files:** 4 created, 15 modified

## Accomplishments

- **WR-03 (second half) closed.** `lifecycle.cancel` accepts `running`: one compare-and-set on `status running` with no `cancelRequested` stamps `{by, at}`; the control row `rollout_cancel_requested` is written (the stamp is put back if it cannot be); `_close_open_rows` (which already covered `approved`) closes every open and approved-not-sent row `rollout_closed`; `_end_unfetched` ends instructions no computer fetched for every ring. The answer is `{"status": "cancelling"}`. If a tick halted the rollout first, the halted path is taken; if a request exists already, 409.
- **No revert, no restart (D-16).** `cancelling.tick` runs after the normal settle passes (install results, restart results) and decides nothing: no install, line, ring advance, verdict, dispatch or halt. `lifecycle.halt` itself now refuses a rollout with `cancelRequested`, so even a failure that settles during the cancel (including 84-27's `rollout_no_result`) cannot halt the ring or start a D-14/D-15 revert.
- **Bounded end.** When no host is `installing` or `restarting`, or `now >= cancelRequested.at + RESULT_DEADLINE` (the 84-27 constant, read from `inflight`, not redefined), `lifecycle.finish_cancel` ends it: status cancelled, rings that did not pass cancelled, claims released, one control row and audit event naming the requester (`cancelledBy`). Hosts still in flight at the bound end `failed` / `rollout_no_result` with their row and job closed. Boundary tested: at the bound minus 1 s the rollout is still running with `cancelRequested`, at plus 1 s it is cancelled.
- **Shared completion.** The old halted-cancel body became `finish_cancel(db, tenant, rollout, who, now, expect=...)`, used by the halted path (unchanged behaviour) and the controller.
- **Resume refused while cancelling.** `resume` raises `CancelRequested` (409, `API_DETAIL["cancel_requested"]`) before any other check, for both a running and a (forced) halted rollout with `cancelRequested`; a second Cancel answers the same 409.
- **Server flags and dialog.** Card fields: `canCancel` is true for running or halted (not while cancelling), `canResume` false while cancelling, `cancelNote` is the server sentence only for a running rollout not yet cancelling. The running card shows a `Cancel rollout` button (`RunningCancel`); `CancelDialog` renders `note` and, on a `cancelling` answer, toasts "Cancelling ... It ends when the installs in progress finish." The halted block and the 84-16/84-18 halted Cancel are unchanged.

## 84-27 hand-offs checked

- **`waiting` / `not_approved` after a denied or expired approval:** Cancel needs no special handling (such a host is not in flight; its claim is released by `finish_cancel`; the closed row reads `rollout_closed`, which settle already treats as `not_approved`). **Resume** of a halted rollout still leaves that host `waiting` until a new line is raised; that is a Resume semantics question, untouched here and left for review (84-29 / re-verification).
- **Reboot row stuck `dispatching` with no instruction:** at completion `cancelling._end_unsent` fails any row of the rollout still `dispatching` with no instruction (`rollout_closed`), so a cancelled rollout no longer leaves one claimed for ever. Only rows with no instruction are touched; restarts already on a computer are left to `reboots.settle` while the cancel waits.
- **84-25 service baseline:** no interaction with Cancel; nothing changed.

## TDD record

- **RED** (`a1960e67c`): the seven tests that exercise the new behaviour failed on the planned assertion for the intended reason (`NotHalted: This rollout is not halted.` from `lifecycle.cancel` on a running rollout; the route answered 409 instead of 200). Two guard tests (halted Cancel unchanged, finished rollout refused) passed at RED as intended. No load, fixture or syntax fault.
- **GREEN** (`41af2a7c8`): 9/9 in `test_patch_rollout_cancel_running.py`; the whole `test_patch_rollout_*.py` set (437 tests, including the new views file) passes on a private mongod on port 27998 (stopped afterwards). A mutation check (the controller branch disabled) fails the four controller tests.
- Task 2 (`f6d8e13f5`) was written implementation-first; RED was then shown after the fact by restoring the HEAD `views.py` and `RolloutCard.tsx`: 3 of 4 backend flag tests and 3 of 5 vitest cases fail without the change, and pass with it.
- Frontend: `npx vitest run src/__tests__` 108 files / 1,604 tests pass; `tsc --noEmit` and eslint `--max-warnings 0` on the touched files are clean. `ruff --select F` is clean on the rollout package.

## Commits

| Hash | Message |
|------|---------|
| a1960e67c | test(84-28): add failing tests for Cancel of a running rollout |
| 41af2a7c8 | feat(84-28): Cancel of a running rollout stops new work, reverts nothing and ends once installs settle |
| a0205e66b | docs(84-28): controller docstring names the cancel bound |
| f6d8e13f5 | feat(84-28): the server offers Cancel while a rollout runs and the dialog says what will happen |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] New tests in new files, not the 498/514/519-line ones**
- **Found during:** Task 1 and 2
- **Issue:** `test_patch_rollout_lifecycle.py` (498), `test_patch_rollout_views.py` (514) and `PatchRolloutDialogs.test.tsx` (519) are at or over the 500-line rule.
- **Fix:** tests A, B, B2, C, D live in `test_patch_rollout_cancel_running.py`; the flag cases in `test_patch_rollout_views_cancel.py`; the dialog cases in `PatchRolloutCancelRunning.test.tsx`. Three existing assertions that pinned "Cancel of a running rollout is refused" were updated in place (lifecycle test twice, views test once, the dialogs test once) to match the new rule.
- **Commits:** a1960e67c, 41af2a7c8, f6d8e13f5

**2. [Rule 3 - Blocking] The running card had no place to render a Cancel button**
- **Found during:** Task 2
- **Issue:** the plan treated `components/patchRollouts/RolloutCard.tsx` as read-only, but Cancel only rendered inside the halt block, so `canCancel` on a running card would show nothing.
- **Fix:** `RunningCancel` (in `RolloutDialogs.tsx`) is rendered by a 3-line addition in `RolloutCard.tsx` for a running card with `canCancel` and `onChanged`.
- **Commit:** f6d8e13f5

**3. [Plan wording] `cancelNote` is a card field, not a page flag**
- The plan said `flags.cancelNote`; `canCancel`/`canResume` are fields of the rollout card (`RolloutCard` in `types.ts`, `rollout_card` in `views.py`), and the note is per rollout. `cancelNote` sits beside them; the card/types key-equality test passes.

**4. [Plan wording] Bound logic lives in `cancelling.py`, a new module**
- `lifecycle.py` would have passed ~500 lines. The in-flight check, `RESULT_DEADLINE` use (via `inflight`), abandon and tick are in `rollout/cancelling.py`; `lifecycle.py` (450) keeps `cancel`, `finish_cancel`, `resume`. The acceptance grep for `RESULT_DEADLINE` in `controller.py` matches its docstring (the constant is imported in `cancelling.py`, not defined twice).

**5. [Plan wording] Control event label**
- The request writes a distinct control event `rollout_cancel_requested` (label added to `CONTROL_LABELS`); completion writes `rollout_cancelled` naming the requester, as planned.

**Total deviations:** 2 auto-fixed (blocking), 3 wording. **Impact:** none on scope.

## Left for review

- **Resume after a denial** (see hand-offs above): a host left `waiting` / `not_approved` stays so after Resume until a new line is raised.
- **Cancel of a completed rollout** still answers the existing "This rollout is not halted." sentence; a more exact "can no longer be cancelled" sentence was not added (the UI never offers the button there).
- **UI is not published** (dist-new only): the running-card Cancel button and dialog sentence need a look on the real screen.

## Known Stubs

None.

## Threat Flags

None. No new endpoint, auth path or schema collection; T-84-77 (same guards on the route; a running Cancel only closes rows and ends unfetched instructions, queues no revert or restart) and T-84-78 (compare-and-set, no decisions or verdicts while cancelRequested, Resume 409, claims released only after in-flight work settles or at RESULT_DEADLINE) are mitigated as planned.

## Self-Check: PASSED

- Created files present: cancelling.py, test_patch_rollout_cancel_running.py, test_patch_rollout_views_cancel.py, PatchRolloutCancelRunning.test.tsx.
- Commits a1960e67c, 41af2a7c8, a0205e66b, f6d8e13f5 are ancestors of HEAD.
- Acceptance greps: `cancelRequested` in lifecycle.py and controller.py; `cancel_requested` in messages.py and lifecycle.py; `RESULT_DEADLINE` in controller.py (docstring) and cancelling.py; `running or halted` in patch_rollout_endpoints.py; `cancelNote` in views.py, types.ts, RolloutDialogs.tsx, the dialog test and the views tests.
- Every changed source file under 500 lines (lifecycle.py 450, views.py 447).
- Private mongod on port 27998 stopped.
