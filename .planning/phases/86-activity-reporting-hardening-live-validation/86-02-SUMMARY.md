---
phase: 86-activity-reporting-hardening-live-validation
plan: 02
subsystem: testing
tags: [pytest, mongodb, autonomous-ops, stop-switch, drill, patch-rollouts, service-desk, watchdog]

requires:
  - phase: 81-autonomy-gate-stop-switch-activity-ledger
    provides: stop.press / stop.clear, gate._stopped, delivery hold-back, approvals (GATE-06)
  - phase: 82-85
    provides: the actors the drill drives (sweep, rollouts, service desk, retention, watchdog sync)
provides:
  - one automated stop drill across every automatic actor, platform scope and tenant scope, with resume
  - a control test that proves the drill world really acts when no stop is on
affects: [86-10 go-live document (check 5 is the live half of D-13), 86-verify]

actuals:
  tokens: 6250
  tasks: 2
  commits: 2

plan_head_before: 18a60f5019231aca79c9d6ba3fb4b9f31ae92727
plan_head_after: b621d4e8bd643f1b905e78790447971a485b553b

tech-stack:
  added: []
  patterns:
    - "one _world per tenant plus one check helper per actor, reused by the platform, tenant, resume and control tests"
    - "a control test (nothing stopped, every actor acts) next to the stop tests so a halt can never pass vacuously"

key-files:
  created:
    - backend/tests/test_autonomous_ops_stop_drill.py
  modified: []

key-decisions:
  - "The drill needed no production change: every actor already halted, so PROH-86-05 never triggered"
  - "The watchdog is driven through the real backend answer (selfheal.sync_response) fed to omni_watchdog sync.resolve_stop and restart.decide, not a hand-written stop dict"
  - "Retention is asserted to keep running and delete during a platform stop (the documented Phase 82 exception), not to pause"

patterns-established:
  - "Drill checks take (stopped tenants, running tenants) so one helper serves the platform stop, a tenant stop and the control run"

requirements-completed: [GATE-06]

coverage:
  - id: D1
    description: "Platform stop through stop.press halts the sweep, cancels the queued stamped instruction (undo still delivered), makes approve answer stopped (deny works), freezes the running rollout with no decision or refused row, and hands the waiting desk ticket to a person with desk_stopped"
    requirement: GATE-06
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_stop_drill.py#test_platform_stop_*"
        status: pass
    human_judgment: false
  - id: D2
    description: "Tenant stop of t1 does the same for t1 while t2 in the same database decides, delivers, approves, advances its rollout and gets its desk reply"
    requirement: GATE-06
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_stop_drill.py#test_tenant_stop_*"
        status: pass
    human_judgment: false
  - id: D3
    description: "Retention keeps running during a platform stop and the watchdog reads the stop from the database source and pauses restarts only"
    requirement: GATE-06
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_stop_drill.py#test_platform_stop_does_not_pause_retention_the_documented_exception"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_stop_drill.py#test_platform_stop_reaches_the_watchdog_through_the_database_source_and_pauses_restarts"
        status: pass
    human_judgment: false
  - id: D4
    description: "After stop.clear for each scope the next sweep decides once and repeats nothing, the frozen rollout is offered again as attempt 2 (never the cancelled instruction), the pending card stays pending, and the desk queues the ticket; an unreadable stop counts as stopped"
    requirement: GATE-06
    verification:
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_stop_drill.py#test_resume_after_*"
        status: pass
      - kind: integration
        ref: "backend/tests/test_autonomous_ops_stop_drill.py#test_a_stop_that_cannot_be_read_counts_as_stopped_for_every_gate"
        status: pass
    human_judgment: false
  - id: D5
    description: "The live half of the drill (a real agent poll, real approvals in a browser, the Ollama reply) is not covered here"
    requirement: GATE-06
    verification: []
    human_judgment: true
    rationale: "Check 5 of the go-live document is walked by the Super Admin on the server (D-14); this suite is the automated half only"

duration: 40min
completed: 2026-11-13
status: complete
---

# Phase 86 Plan 02: Stop Drill Summary

**One hermetic drill (16 tests, private mongod) presses the platform stop and a tenant stop through the real stop.press against the security sweep, agent delivery, approvals, patch rollouts, service desk replies, retention and the watchdog's stop source, and proves a clean resume.**

## Performance

- **Duration:** about 40 min
- **Completed:** 2026-11-13
- **Tasks:** 2 of 2
- **Files:** 1 created (backend/tests/test_autonomous_ops_stop_drill.py, 460 lines)

## Accomplishments

- A `_world` per tenant seeds a ticked tenant (shadow off, undoable_auto) with sweep signals that make the sweep block an address, a queued stamped block and a queued stamped undo for its agent, a pending isolate_host card, a started two-ring patch rollout with its canary install in flight, and a ticket already waiting for the desk. Two tenants (t1, t2) share one database.
- Platform stop tests, one per property: sweep records nothing for either tenant; press cancels the queued block (ledger row cancelled_by_stop) while the undo is still delivered; approve answers `stopped` and deny still works; the rollout loop sets `stoppedSince` and writes no decision, no refused row and no instruction; the desk queues nothing and the worker hands the waiting ticket over with `desk_stopped`, no model request and no AI comment; retention counts, is confirmed and deletes (documented exception); the backend's real sync answer reaches `resolve_stop` as `(True, "database")` and `restart.decide` issues no restart.
- Tenant stop tests for t1 with t2 deciding its block, getting its queued block and undo, approving its card, advancing its rollout to ring 1's approval line and receiving its desk reply in the same pass.
- Resume tests for both scopes: after `stop.clear` the next sweep decides exactly once (a second pass repeats nothing), the rollout is offered again as attempt 2 with a new instruction, the pending card is still pending with no approver, and the desk queues the ticket refused during the stop.
- A fail-closed test (an unreadable platform stop makes `gate._stopped`, approve, the sweep and delivery all behave as stopped) and a control test (nothing stopped, every actor acts), so no halt assertion can pass vacuously.

## Task Commits

1. **Task 1: Platform stop drill** - `aa8256525` (test)
2. **Task 2: Tenant stop drill, other tenant unaffected, clean resume** - `b621d4e8b` (test)

## Verification

- Task 1 command (drill + test_autonomous_ops_stop + test_autonomous_ops_structural): 66 passed, no skips.
- Task 2 command (drill + test_patch_rollout_shadow_stop + test_service_desk_intake): 61 passed, no skips.
- Plan verification (sweep, approvals, retention_job, structural, stop): 165 passed, no skips.
- Mutation check: with `stop.press` replaced by a no-op, 13 of the 16 drill tests fail (the three that pass are the control, retention and the fail-closed test, which do not depend on a press).
- Acceptance greps: `stop.press` 1, `stop.clear` 4, `"t2"` 7, `def test_` 16, `27017` 0, 460 lines. All real-MongoDB runs used the private mongod at 127.0.0.1:27998.

## Deviations from Plan

None - plan executed exactly as written. No assertion failed against production code, so no actor was changed (PROH-86-05 not triggered). Minor choices inside the plan: the rollout property uses `rollout.loop.run_once` (the entry point the plan names) and, for the running tenant, drives the canary to ring 1's approval line to show it advances; the desk uses `service_desk_support.ollama_transport` as the fake model client (never the local Ollama); `audit_ledger.event` and `notify.notify` are patched with AsyncMock as the plan's execution rules require.

## Issues Encountered

None.

## Known Stubs

None.

## Threat Flags

None. The plan adds a test file only; T-86-04 (an actor ignoring the stop) is mitigated by the drill and found no gap.

## Next Phase Readiness

Ready for the remaining Phase 86 plans. The live half of D-13 (go-live check 5) stays the Super Admin's step in 86-10.

## Self-Check: PASSED

- backend/tests/test_autonomous_ops_stop_drill.py: FOUND
- aa8256525: FOUND
- b621d4e8b: FOUND
