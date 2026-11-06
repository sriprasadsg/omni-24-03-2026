---
phase: 84-staged-patch-rollouts
plan: 04
subsystem: autonomous-ops
tags: [patch-rollout, delivery, instruction-expiry, reconciler, legacy-fence, mongodb, python]

requires:
  - phase: 84-staged-patch-rollouts
    provides: 84-01 controller and install rows; 84-03 dispatcher that writes install instructions with expiresAt at the occurrence end
  - phase: 81-autonomous-ops-safety-core
    provides: delivery.hold_back_autonomous, the reconciler, GRANDFATHERED_WRITERS structural test
provides:
  - "delivery.hold_back_autonomous refuses a pending instruction whose expiresAt has passed (error instruction_expired) on all three agent poll paths"
  - "reconciler skips patch_rollout rows in _reconcile_dispatches; awaiting_approval rollout cards still expire"
  - "deployment_service.LegacyRevertRetired; trigger_rollback writes nothing; POST /api/deployments/{id}/rollback answers 409 pointing to Rollouts"
  - "deployment_service.py removed from GRANDFATHERED_WRITERS, so a regression fails the structural test"
affects: [84-08, 84-10, 84-13, 84-22]

requirements-completed: [PTCH-07, PTCH-05]

actuals:
  tokens: 8000
  tasks: 3
  commits: 6
plan_head_before: 14ec94d80ff7c6c10a6f3ffaad08e7204df39482
plan_head_after: 237cdc5675c4b558efbe181f8c7a031b0fa85036

tech-stack:
  added: []
  patterns:
    - "expiry is the item's own clock, checked first in hold_back_autonomous; a batch with no expiresAt still costs zero database calls"
    - "a dispatcher that owns its settle is skipped by name in _reconcile_dispatches (remediation multi-step rows, now patch_rollout)"

key-files:
  created:
    - backend/tests/test_patch_rollout_delivery.py
    - backend/tests/test_patch_rollout_legacy_fence.py
  modified:
    - backend/autonomous_ops/delivery.py
    - backend/autonomous_ops/reconciler.py
    - backend/deployment_service.py
    - backend/deployment_endpoints.py
    - backend/tests/test_autonomous_ops_reconciler.py
    - backend/tests/test_autonomous_ops_structural.py

key-decisions:
  - "Expiry applies to any item carrying a datetime expiresAt (stamped or not); a value that is not a date is ignored rather than dropping work; naive datetimes (what Mongo returns) are read as UTC"
  - "A stamped undo or compensate is exempt from expiry even if it carried an expiresAt (D-15), as it is exempt from the stop"
  - "install_patches was not added to GATE_ONLY_COMMANDS: the manual deploy routes send the same command unstamped"
  - "The rollout dispatcher constant is imported into the reconciler from the stdlib-only rollout package rather than repeated as a literal"
  - "The automatic revert on a failed legacy stage (rollback_on_failure) now ends with the stage left failed and nothing queued"

patterns-established:
  - "Refusing a pending queue item is one helper (delivery._refuse) shared by the unstamped gate-only refusal and the expiry refusal"

coverage:
  - id: D1
    description: "An agent instruction whose expiresAt is at or before now is never delivered by any of the three poll paths; it is marked refused with error instruction_expired. One inside its window is delivered as before"
    requirement: PTCH-07
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_delivery.py#test_an_expired_instruction_is_absent_from_every_poll_response"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_delivery.py#test_an_instruction_past_its_expiry_is_refused_and_not_delivered"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_delivery.py#test_a_naive_expiry_is_read_as_utc"
        status: pass
    human_judgment: false
  - id: D2
    description: "A batch with no stamped item, no gate-only item and no expiresAt is returned unchanged with zero database calls; an undo is delivered during a stop and whatever its clock"
    requirement: PTCH-07
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_delivery.py#test_a_plain_batch_with_no_expiry_is_returned_unchanged_and_touches_no_database"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_delivery.py#test_an_undo_is_delivered_during_a_stop_and_whatever_its_clock"
        status: pass
    human_judgment: false
  - id: D3
    description: "The reconciler never fails or settles a patch_rollout row (approved row 2 h old, dispatching row with an accepted instruction 25 h old), while an awaiting_approval rollout card still expires; other dispatchers keep their mapping (control rows in the same tests)"
    requirement: PTCH-05
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_reconciler.py#test_an_approved_rollout_row_waiting_for_its_window_is_not_failed"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_reconciler.py#test_a_dispatching_rollout_row_with_an_accepted_instruction_is_not_failed_no_result"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_reconciler.py#test_a_rollout_row_waiting_for_a_person_still_expires_after_the_card_lifetime"
        status: pass
    human_judgment: false
  - id: D4
    description: "The legacy staged-deployment revert writes nothing to agent_instructions or rollback_jobs: the service refuses, a failed stage stays failed, the route answers 409 with the pointer to Rollouts, and deployment_service.py is no longer a grandfathered queue writer"
    requirement: PTCH-07
    verification:
      - kind: integration
        ref: "backend/tests/test_patch_rollout_legacy_fence.py#test_trigger_rollback_refuses_and_writes_no_instruction"
        status: pass
      - kind: integration
        ref: "backend/tests/test_patch_rollout_legacy_fence.py#test_the_route_answers_409_with_a_pointer_to_rollouts"
        status: pass
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_structural.py#test_queue_writers_are_grandfathered"
        status: pass
    human_judgment: false

duration: 9min
completed: 2026-11-06
status: complete
---

# Phase 84 Plan 04: Side doors around rollouts Summary

**Instruction expiry at delivery (instruction_expired on all three poll paths), rollout rows left to their controller by the reconciler, and the legacy staged-deployment revert fenced with a 409 and removed from the grandfathered queue writers**

## Performance

- **Duration:** 9 min
- **Started:** 2026-11-06T14:53:49Z
- **Completed:** 2026-11-06T15:02:00Z
- **Tasks:** 3
- **Files modified:** 8 (2 created)

## Accomplishments
- An install or restart that waited in the queue past its window can no longer run when a host comes back online: `hold_back_autonomous` refuses it before any other check, on the live tasks poll, the deployment-result poll and the unmounted instruction poll (all three call the same hook, already pinned by the structural test).
- The reconciler no longer fails an approved rollout install after 30 minutes (it waits for its window) nor a sent one after 24 hours (it reports through the deployments route). Awaiting-approval rollout cards still expire. Each new test carries a control row of another dispatcher that is still failed, proving the test can fail.
- The old revert that wrote ungated `rollback_patches` instructions is gone; the only automatic revert is the gated rollout revert. `deployment_service.py` leaves `GRANDFATHERED_WRITERS`, and the rot check now proves it writes no queue.

## Task Commits

1. **Task 1: Expired instructions are never delivered** - `c0bd18404` (test), `a9c7dadf4` (feat)
2. **Task 2: The reconciler leaves rollout rows to the controller** - `04137475e` (test), `b472582c5` (feat)
3. **Task 3: The legacy staged-deployment revert is fenced** - `1ec2222a7` (test), `237cdc567` (feat)

**Plan metadata:** committed with this summary (docs)

## Files Created/Modified
- `backend/autonomous_ops/delivery.py` - expiry check first in hold_back_autonomous; shared `_refuse` helper; docstring rule (196 lines)
- `backend/autonomous_ops/reconciler.py` - skips `patch_rollout` rows in `_reconcile_dispatches`; docstring names the owner
- `backend/deployment_service.py` - `LegacyRevertRetired`; `trigger_rollback` raises; `update_stage_progress` swallows it so a failed stage stays failed; unused `uuid` import removed
- `backend/deployment_endpoints.py` - maps `LegacyRevertRetired` to 409 with the Rollouts sentence
- `backend/tests/test_patch_rollout_delivery.py` - 14 tests (rule, naive datetimes, boundary, bad value, undo exemption, three poll paths)
- `backend/tests/test_patch_rollout_legacy_fence.py` - service, failed-stage and route tests
- `backend/tests/test_autonomous_ops_reconciler.py` - three added tests (no existing assertion edited)
- `backend/tests/test_autonomous_ops_structural.py` - `deployment_service.py` removed from `GRANDFATHERED_WRITERS`

## Decisions Made
See key-decisions above. The plan was followed as written; the points the plan left open (non-date values, undo with an expiry, the failed-stage caller) are recorded there.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] The automatic revert path would have raised on a failed legacy stage**
- **Found during:** Task 3
- **Issue:** `update_stage_progress` calls `trigger_rollback` when a stage misses its success rate and `rollback_on_failure` is on. With the fence raising, the call would have escaped and skipped the database update that records the failed stage.
- **Fix:** `update_stage_progress` catches `LegacyRevertRetired`; the stage and deployment are saved as failed and nothing is queued. Covered by `test_a_failed_stage_stays_failed_and_asks_for_no_revert`.
- **Files modified:** backend/deployment_service.py
- **Committed in:** 237cdc567

**2. [Rule 2 - Missing Critical] Expiry exempts stamped undo and compensate**
- **Found during:** Task 1
- **Issue:** The plan relies on undo instructions carrying no `expiresAt`. Nothing enforces that, so a future writer that set one would make a revert subject to a window, against D-15.
- **Fix:** `_expired` ignores items whose stamp kind is in `STOP_EXEMPT_KINDS`; tested with an undo given an old expiresAt during a platform stop.
- **Files modified:** backend/autonomous_ops/delivery.py
- **Committed in:** a9c7dadf4

---

**Total deviations:** 2 auto-fixed (1 bug, 1 missing critical)
**Impact on plan:** Both needed for correctness; no scope change.

## Issues Encountered
- `deployment_service.py` and `deployment_endpoints.py` are CRLF in the working tree (LF in the index, `eol=lf`); edited with line endings preserved so the diff holds only the plan's changes.
- The pre-existing route wraps its 403 in a blanket `except Exception` that turns it into a 500. Left alone (out of scope); the new 409 clause sits before that handler.

## Known Stubs
None.

## Threat Flags
None. T-84-12, T-84-13 and T-84-14 mitigated as registered; T-84-15 accepted (undo stays stop-exempt).

## User Setup Required
None - no external service configuration required. Nothing was restarted or published; the backend runs these changes only after the user's next restart.

## Next Phase Readiness
Ready for the next wave-2 plan. The dispatcher's `expiresAt` (84-03) is now enforced at delivery, and the reconciler no longer competes with the rollout controller for settling rollout rows.

## Self-Check: PASSED

- Files: delivery.py, reconciler.py, deployment_service.py, deployment_endpoints.py, both new test files present.
- Commits: c0bd18404, a9c7dadf4, 04137475e, b472582c5, 1ec2222a7, 237cdc567 are ancestors of HEAD.
- Verification (private mongod on 27998, stopped afterwards): 251 passed across the delivery, legacy-fence, rollout (contract, dispatcher, lines, tracer, messages), reconciler, stop, structural and approvals suites; no skips.
- Acceptance: `instruction_expired` in delivery.py; delivery.py 196 lines; `patch_rollout` in reconciler.py; no existing reconciler assertion edited; `"deployment_service.py"` count in structural test is 0; `LegacyRevertRetired` count in deployment_service.py is 3.

---
*Phase: 84-staged-patch-rollouts*
*Completed: 2026-11-06*
