---
phase: 81-autonomy-gate-stop-switch-activity-ledger
plan: 18
subsystem: autonomous-ops
tags: [approvals, never-touch, undo, ledger, pytest, gap-closure]

requires:
  - phase: 81-autonomy-gate-stop-switch-activity-ledger (81-13)
    provides: ledger rows record steps and rollback; ip_refusal; multi-step rows record undo.available False
  - phase: 81-autonomy-gate-stop-switch-activity-ledger (81-15)
    provides: gate.execute binds every dispatch to the decided row through dispatch_check.bind
provides:
  - "dispatch_check.row_pairs(row): (spec, own params) for every recorded step then every compensation step; pre-81-13 rows fall back to command plus params"
  - "dispatch_check.step_count(row)"
  - "approvals._revalidate re-checks the never-touch list over every recorded step and compensation step"
  - "approvals.undo returns no_undo for a row decided with more than one step"
affects: []

actuals:
  tokens: 9000
  tasks: 2
  commits: 2

plan_head_before: 41557f2640146fec84683be02a0f2fc37cd18cb3
plan_head_after: 154fd01b83800046f37cbbf5ed96648fe7031343
commits: 2

tech-stack:
  added: []
  patterns:
    - "Approval re-check and decide-time check share one function (ip_refusal) over different pair sources (spec_pairs / row_pairs)"

key-files:
  created: []
  modified:
    - backend/autonomous_ops/dispatch_check.py
    - backend/autonomous_ops/approvals.py
    - backend/tests/test_autonomous_ops_dispatch_binding.py

key-decisions:
  - "A row with a steps list is re-checked from its recorded steps and rollback only; a row without one is re-checked from actions (else command) with the row params, exactly as before"
  - "step_count counts the recorded steps; a legacy row with a command counts as one step so its undo is unchanged"

requirements-completed: [GATE-08, GATE-10, ACTV-01]

duration: 12min
completed: 2026-10-26
status: complete
---

# Phase 81 Plan 18: Approval-time step re-check and multi-step undo refusal Summary

**Approving a multi-step card now re-checks every recorded step and compensation step against the current never-touch list, and a multi-step row can no longer read Undone after one undo instruction (closes the approval half of CR-01).**

## Accomplishments

- A never-touch entry added after a two-step card was created, for the IP of its second step, makes `approvals.approve` return refused `protected_target`: the row moves to `refused` with that reasonCode and zero `agent_instructions` are written. The same holds for the last of three steps and for a compensation step. Without the entry the same card dispatches.
- An unreadable never-touch list during the re-check refuses `protected_target` (the existing fail-closed `except` in `_revalidate` is kept). A legacy row (no `steps`) is re-checked from command plus params and refuses a late entry too.
- `approvals.undo` returns `no_undo` for a row decided with more than one step; the row stays `executed` and no instruction is written. Single-step and legacy rows undo exactly as before.

## Task Commits

1. Task 1 (tracer): `17e7212d7` fix(81-18): approval re-checks every recorded step and compensation step against the never-touch list
2. Task 2: `154fd01b8` fix(81-18): a multi-step row cannot be undone by one instruction

## Metrics

- approvals.py: 242 lines before, 240 after. dispatch_check.py: 174 before, 197 after (cap 500). gate.py untouched.
- New tests in test_autonomous_ops_dispatch_binding.py (362 to 471 lines): 11 (real throwaway Mongo).
- No test file other than test_autonomous_ops_dispatch_binding.py changed; `git diff --stat -- backend/tests/test_autonomous_ops_approvals.py` is empty and that suite passes unchanged.

## Verification

- Task 1 verify (dispatch_binding, approvals, isolation, structural): 105 passed, 0 skipped.
- Task 2 verify command 1 (dispatch_binding, approvals, isolation, remediation_guards, ueba_remediation_trigger, autonomous_remediation_loop): 135 passed, 0 skipped.
- Task 2 verify command 2 plus xdr (`-k "autonomous_ops or remediation or ueba or xdr or rotate_key"` over backend/tests): 551 passed, 4066 deselected.
- `tests/test_autonomous_ops_*.py` on its own: 430 passed, 0 skipped.

## Deviations from Plan

None - plan executed exactly as written. The RED run showed the second-step, last-step, compensation-step and multi-step-undo tests failing before the code change; the plan's fail-closed and legacy-row cases passed already, as expected (existing behaviour).

## Known Stubs

None.

## Threat Flags

None. T-81-52 and T-81-53 are mitigated by this plan.

## Notes for the user

- Steps for the user: none. No restart, migration or live-database action was taken; the backend runs from this checkout and picks the change up on its next restart.
- Phase 81 gap-closure plans 81-13..81-18 are now all executed; the phase is ready for re-verification (`/gsd-verify-work 81` or the verifier).

## Self-Check: PASSED

- backend/autonomous_ops/dispatch_check.py (row_pairs, step_count), approvals.py (row_pairs, step_count uses) and the test module: present.
- Commits 17e7212d7 and 154fd01b8: present in HEAD history.
