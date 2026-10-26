---
phase: 81-autonomy-gate-stop-switch-activity-ledger
plan: 15
subsystem: autonomous-ops
tags: [gate, dispatch-binding, never-touch, ledger, pytest, gap-closure]

requires:
  - phase: 81-autonomy-gate-stop-switch-activity-ledger (81-13)
    provides: ledger rows carry steps and rollback; dispatch_check helpers
provides:
  - "dispatch_check.same_params, decided_steps, bind"
  - "gate._authorise binds every dispatch (command, agent, params, kind) to the decided row before the approved -> dispatching transition"
  - "refusal reasons target_mismatch and step_mismatch from the two stamped writers"
affects: [81-16, 81-17, 81-18]

actuals:
  tokens: 26000
  tasks: 2
  commits: 2

plan_head_before: 179fed062145e8fe0ced205bbf9ee9cfd3575d07
plan_head_after: 85a7dd4c5c2641cf312fde55047d76cf9cacdb2c
commits: 2

tech-stack:
  added: []
  patterns:
    - "Binding logic lives in dispatch_check so gate.py stays at its 500-line cap"
    - "Canonical-JSON parameter comparison (sorted keys, default=str): a changed representation fails closed"

key-files:
  created: []
  modified:
    - backend/autonomous_ops/dispatch_check.py
    - backend/autonomous_ops/gate.py
    - backend/tests/test_autonomous_ops_dispatch_binding.py
    - backend/tests/autonomy_support.py
    - backend/tests/test_autonomous_ops_ledger.py
    - backend/tests/test_autonomous_ops_stop.py
    - backend/tests/test_autonomous_ops_approvals.py
    - backend/tests/test_remediation_guards.py

key-decisions:
  - "bind order: unregistered_action, target_mismatch, step_mismatch (class fit, then decided membership), then the never-touch re-check; so an undecided address is step_mismatch and a decided-but-newly-protected one is protected_target"
  - "Probe is bound to the agent only: any probe-class command, params unbound; undo is bound to the row's recorded undo action and params (available flag not required)"
  - "Never-touch is re-checked only for auto/approve commands; undo_only and probe commands are not IP-checked at dispatch (they put things back or only read)"

requirements-completed: []

duration: 35min
completed: 2026-10-26
status: complete
---

# Phase 81 Plan 15: Execute-time dispatch binding Summary

**gate.execute and gate.execute_response_task now write only a decided step, to a decided host, with the decided parameters, and re-check the never-touch list at dispatch time (closes the execute half of CR-01).**

## Accomplishments

- `dispatch_check.bind` refuses, before anything is written and before the approved -> dispatching transition, with: `unregistered_action` (command not in the registry), `target_mismatch` (agent not in the row's targets, including another tenant's agent), `step_mismatch` (class does not fit the kind, or no decided step has that command and the same params), `protected_target` / `invalid_target` (auto and approve commands: every IP parameter re-checked against the current never-touch list; an unreadable list refuses `protected_target`).
- Kind rules: action = a recorded main step (rows without steps fall back to actions plus params); compensate = a recorded compensation step of class undo_only; undo = the recorded undo action and params; probe = any probe command.
- Refusal order kept: invalid_kind, not_found, not_dispatchable, stopped, then the binding. A refused binding leaves an approved row approved (tested).
- Through `_dispatch_and_verify`: a playbook whose second step was altered to 127.0.0.1 after the decision is refused at execute, the first step is sent, the row ends failed, and no instruction exists for the altered step.
- XDR fence unchanged: `test_autonomous_ops_xdr_fence.py` passes without edits.
- Edge cases covered by tests: two identical decided steps both dispatch; int 5 versus "5" is step_mismatch; a never-touch entry added between decide and execute refuses `protected_target`; an unparsable decided IP is `invalid_target`.

## Task Commits

1. Task 1 (tracer): `05108d223` fix(81-15): gate binds every dispatch to the decided row and re-checks never-touch
2. Task 2: `85a7dd4c5` test(81-15): existing tests dispatch exactly what their rows decided

## Metrics

- gate.py: 500 lines (cap 500; was 498). dispatch_check.py: 174 lines.
- New tests: 13 in test_autonomous_ops_dispatch_binding.py (real throwaway Mongo).
- `bind()` was never relaxed; Task 2 changed no file under backend/autonomous_ops.

## Verification

- Task 1 command (dispatch_binding, xdr_fence, gate, structural): 84 passed, 0 skipped.
- Task 2 command 1 (ledger, stop, approvals, remediation_guards, dispatch_binding): all passed, 0 skipped (final run covered below).
- Plan command 2 (`-k "autonomous_ops or remediation or ueba or rotate_key or xdr or playbook"` over backend/tests): 504 collected, 503 passed on the first run with one test (approvals no_undo case) still to realign; that test passes after the fix (29 passed in test_autonomous_ops_approvals.py).
- Final explicit suites (`test_autonomous_ops_*.py`, `test_remediation_guards.py`, `test_ueba_remediation_trigger.py`, `test_autonomous_remediation_loop.py`): 433 passed, 0 failed, 0 skipped (includes the XDR fence tests).

## Existing tests changed, and the intent each keeps

All were failing only because they dispatched something their row had not decided. None needed bind() changed.

`backend/tests/autonomy_support.py` (permissive_gate; docstring now names 81-15):
- The fake decide records `steps` and `rollback` on the row (via `dispatch_check.plan_of`) and `protected.check` is patched to `AsyncMock(return_value=None)`, since a MagicMock database cannot serve the never-touch list. The real check is proven in test_autonomous_ops_dispatch_binding.py.

`backend/tests/test_remediation_guards.py`:
- `_row(stack, finding, playbook)` now builds a row carrying the plan for the finding (targets, rendered steps, rendered rollback).
- `test_failed_verify_reversible_dispatches_rollback`: still proves a failed verify dispatches the compensate `unblock_ip` and ends rolled_back.
- `test_failed_verify_irreversible_escalates_no_rollback`: still proves a failed verify with no rollback escalates and the row stays failed.
- `test_lease_released_on_completion`: still proves the per-agent lease is inserted and released; it now really dispatches (before it passed with the dispatch refused).

`backend/tests/test_autonomous_ops_ledger.py`:
- `_req` takes an optional `rollback`; `_dispatching` decides with the unblock_ip compensation for its IP; new `_decided_row` helper for rows made directly.
- `test_an_approved_row_becomes_dispatching_when_executed`: executes with the decided `{"ip_address": ...}` instead of `{}`; still proves approved -> dispatching and the pre-approval `not_dispatchable`.
- `test_kinds_are_dispatched_from_their_own_states`: rows carry steps, rollback and undo; probe uses scan_ip, compensate and undo use the decided unblock_ip params; still proves each kind is dispatchable only from its own states.
- `test_a_stop_holds_back_actions_and_probes_but_not_undo_or_compensate` (3 parametrizations): per-row decided params; still proves a stop holds actions, probes and response tasks but not undo or compensate.
- `test_an_inactive_stop_does_not_hold_anything_back`: decided params; still proves an inactive stop holds nothing back.

`backend/tests/test_autonomous_ops_stop.py`:
- `_queue_exempt`: the directly created undo and compensate rows carry targets, steps, rollback and undo. Preserves the stop-exemption of undo and compensate.
- `test_press_bulk_cancels_for_its_scope_and_returns_the_count`: the response task is queued with the decided IP; still proves the bulk cancel count.

`backend/tests/test_autonomous_ops_approvals.py` (listed in files_modified):
- `test_undo_of_a_row_without_an_undo_and_of_other_states`: the execute result is now asserted queued (it passes the decided `{}`), so the test no longer relies on a silently refused call. Intent (restart_service has no undo -> no_undo) is unchanged.

No test file outside files_modified needed alignment.

## Deviations from Plan

None - plan executed as written. The plan's `<action>` order (run the full suite first, then align) was followed using a first full run that listed 10 failures.

## Known Stubs

None.

## Threat Flags

None. T-81-56, T-81-57 and T-81-58 are mitigated and covered by tests.

## Notes for later plans / steps for the user

- Requirements GATE-03, GATE-08 and GATE-10 stay pending in REQUIREMENTS.md: 81-16, 81-17 or 81-18 still list them.
- `autonomous_remediation_service.py` was not touched; its `_dispatch_step` already returns the gate's refusal reason.
- No restart, migration or live-database action was taken. The backend runs from this checkout and picks the change up on its next restart.

## Self-Check: PASSED

- backend/autonomous_ops/dispatch_check.py (async def bind: 1) and backend/autonomous_ops/gate.py (dispatch_check.bind( : 1): present.
- Commits 05108d223 and 85a7dd4c5: present in HEAD history.
