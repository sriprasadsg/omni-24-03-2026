---
phase: 81-autonomy-gate-stop-switch-activity-ledger
plan: 14
subsystem: autonomous-ops
tags: [reconciler, circuit-breaker, settings, ledger, pytest, gap-closure]

requires:
  - phase: 81-autonomy-gate-stop-switch-activity-ledger (81-04)
    provides: reconciler, breaker, settings
  - phase: 81-autonomy-gate-stop-switch-activity-ledger (81-09)
    provides: level route and restore-level route
provides:
  - "reconciler no_result rule: a picked-up but silent instruction fails the row after AUTONOMOUS_OPS_NO_RESULT_MIN (default 1440)"
  - "settings.set_level clears a tripped breaker atomically when set to undoable_auto and records level_restored"
  - "messages.REASON_TEXT['no_result']"
affects: [81-16, 81-17]

actuals:
  tokens: 9000
  tasks: 2
  commits: 2

plan_head_before: 2cab4e0cdc1e3143e3a850e12586c39a62a91f1d
plan_head_after: 33dd9d8003c9c5d54a967dd4254c01369d3deec4
commits: 2

tech-stack:
  added: []
  patterns:
    - "Silent-agent bound: same compare-and-set on updatedAt as the not-delivered rule, a longer env-tunable bound that is never below it"
    - "Atomic level+breaker write with ReturnDocument.BEFORE so the control row is written only when a breaker was actually cleared"

key-files:
  created: []
  modified:
    - backend/autonomous_ops/reconciler.py
    - backend/autonomous_ops/messages.py
    - backend/autonomous_ops/settings.py
    - backend/tests/test_autonomous_ops_reconciler.py
    - backend/tests/test_autonomous_ops_breaker.py

key-decisions:
  - "WR-02 discretion choice: setting Undoable-auto by hand clears the tripped breaker in the same update (rather than refusing the change). The level route already requires manage:autonomous_ops, so a person with the permission restores the level (D-18); suggest and off keep the breaker so restore-level still works."
  - "The no_result branch applies to any non-empty status that is not pending/queued and not a final outcome (sent, delivered, in_progress, running, unknown words): fail closed after the bound."
  - "set_level now returns Dict[str, Any]; the key breakerCleared appears only when a breaker was cleared, so the route (unchanged) still returns status ok."

requirements-completed: []

duration: 25min
completed: 2026-10-26
status: complete
---

# Phase 81 Plan 14: no_result bound and breaker-aware set_level Summary

**A row whose instruction was picked up but never reported now fails as no_result after 24 h (env-tunable), and raising the level by hand re-arms a tripped circuit breaker with a level_restored audit row (closes WR-01 and WR-02).**

## Accomplishments

- Reconciler: `_DEFAULT_NO_RESULT_MIN = 1440`, `_no_result_after()` (env `AUTONOMOUS_OPS_NO_RESULT_MIN`, invalid/zero/negative falls back to 1440, never shorter than the not-delivered bound). The dispatching to failed move carries `where={"updatedAt": {"$lte": cutoff}}`, so a concurrent agent result is not overwritten. Failure releases the dedupe slot (a new `gate.decide` with the same key is recorded) and the existing "rows changed" path asks the breaker to evaluate; three no_result failures trip it. pending/queued rows keep the 30-minute `not_delivered` rule; a sent row at 31 minutes stays dispatching. Cutoff is inclusive to the second.
- `messages.REASON_TEXT["no_result"]` in plain words; copy tests (pytest and vitest) pass.
- `settings.set_level(..., "undoable_auto")` writes level and `breaker: None` in one `find_one_and_update` (`ReturnDocument.BEFORE`); when a breaker document existed, a `level_restored` control row is recorded with the person as actor (a ledger failure is logged and does not undo the level change, mirroring `breaker.restore`). The breaker can trip again on three newer bad outcomes. `above_max` still changes nothing. The level route (`autonomous_ops_endpoints.py`) is unchanged.
- Reconciler still never calls `breaker.restore` (D-18).

## Instruction status values observed in the poll endpoints

- `backend/agent_tasks_endpoints.py` sets `sent` (with `sent_at`) when an agent polls an instruction.
- `backend/deployment_result_endpoints.py` sets `delivered`.
- Result endpoints store SUCCESS / FAILURE or the agent's own word upper-cased; the reconciler lower-cases and maps them (existing sets), everything else non-empty falls to no_result after the bound.

## Task Commits

1. Task 1 (tracer): `d46f470d5` feat(81-14): fail a picked-up but silent instruction as no_result after the bound
2. Task 2: `33dd9d800` fix(81-14): setting Undoable-auto by hand re-arms a tripped breaker

## Verification

- `test_autonomous_ops_reconciler.py`, `_copy.py`, `_gate.py`: 59 passed, 0 skipped. `npx vitest run src/__tests__/autonomousOpsCopy.test.ts`: 18 passed.
- `test_autonomous_ops_breaker.py`, `_endpoints_writes.py`, `_endpoints.py`, `_permissions.py`: 90 passed.
- Whole `test_autonomous_ops_*.py`: 364 passed, 0 skipped.
- `git diff --stat -- backend/autonomous_ops_endpoints.py` empty; `breaker.restore(` call count in reconciler.py is 0.

## Deviations from Plan

None - plan executed exactly as written. One test-only adjustment: the control-row assertion uses `sorted(...)` (as the existing restore test does) because `_controls` returns rows in unspecified order.

## Known Stubs

None.

## Threat Flags

None. T-81-54 (silent agent holds the dedupe slot) and T-81-55 (permanently disarmed breaker) are mitigated and covered by tests.

## Notes for later plans / steps for the user

- Requirements GATE-07, GATE-11, GATE-14 stay pending in REQUIREMENTS.md: 81-16 still lists all three.
- No restart, migration or live-database action was taken. The backend runs from this checkout and picks the change up on its next restart; `AUTONOMOUS_OPS_NO_RESULT_MIN` is optional.

## Self-Check: PASSED

- Modified files present; commits d46f470d5 and 33dd9d800 are in HEAD history.
