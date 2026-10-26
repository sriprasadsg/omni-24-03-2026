---
phase: 81-autonomy-gate-stop-switch-activity-ledger
plan: 13
subsystem: autonomous-ops
tags: [gate, playbook, never-touch, registry, ledger, pytest, gap-closure]

requires:
  - phase: 81-autonomy-gate-stop-switch-activity-ledger (81-04)
    provides: gate.decide, ActionRequest
  - phase: 81-autonomy-gate-stop-switch-activity-ledger (81-08)
    provides: registry classes, GATE-05 structural tests
  - phase: 81-autonomy-gate-stop-switch-activity-ledger (81-11)
    provides: protected.check never-touch list
provides:
  - "backend/autonomous_ops/dispatch_check.py: request_steps, request_rollback, steps_consistent, classify, spec_pairs, plan_of, ip_refusal"
  - "gate.ActionRequest.steps / .rollback; every main step and compensation step class- and IP-checked with its own params"
  - "ledger row fields steps and rollback ([{command, params}] in playbook order); multi-step rows record undo.available False"
affects: [81-14, 81-15, 81-16, 81-17, 81-18]

actuals:
  tokens: 18000
  tasks: 2
  commits: 1

plan_head_before: d477238f0a69024f9de78cb74ebb63844a23eb3e
plan_head_after: 3590f2e6be3e9ed770f021f3293b373a838bdc7a
commits: 1

tech-stack:
  added: []
  patterns:
    - "Gate helper logic lives in dispatch_check so gate.py stays under the 500-line cap"
    - "A request without steps derives them from actions plus shared params inside request_steps: one internal source"

key-files:
  created:
    - backend/autonomous_ops/dispatch_check.py
    - backend/tests/test_autonomous_ops_dispatch_binding.py
  modified:
    - backend/autonomous_ops/gate.py
    - backend/autonomous_remediation_service.py

key-decisions:
  - "The recorded steps list is the authoritative decided plan; the row's command/params are display and undo of the first step (A-81-STEP-PLAN-PROMOTED)"
  - "A multi-step row offers no undo; _undo_block gained a multi flag (approvals.undo still calls it with two arguments) (A-81-MULTISTEP-UNDO)"
  - "A malformed steps or rollback value (non-list, non-dict item) resolves to an unresolvable name and is refused unregistered_action, never skipped"

requirements-completed: [GATE-04]

duration: 20min
completed: 2026-10-26
status: complete
---

# Phase 81 Plan 13: Decide-time playbook step checks Summary

**The gate now class-checks and never-touch-checks every playbook step and every compensation step with its own parameters, and records the decided plan on the ledger row (closes the decide-time half of CR-01).**

## Accomplishments

- A two-step operator playbook whose second step is `block_ip 127.0.0.1` is refused `protected_target` through `remediate()`: one refused row, zero `agent_instructions`. Same for the protected IP in the first, middle and last of three steps, and in a compensation step; an unparsable IP in any step refuses `invalid_target`; an unreadable never-touch list refuses `protected_target`.
- `dispatch_check.classify` checks every main step is registered auto or approve and every compensation step is registered undo_only; undo_only or probe main steps, unregistered names, non-undo_only rollbacks, and steps/actions mismatches (including an empty steps list) are refused `unregistered_action`. One approve step in any position makes the whole request `needs_approval` (`class_approve`); only the explicit `gate_class` key raises otherwise. The vendored block_ip playbook is still `allow_auto`.
- The decided row records `steps` and `rollback` as `[{command, params}]` in playbook order; a row with more than one step records `undo.available` False, action None.
- A benign two-step playbook dispatches both `block_ip` instructions with their own `ip_address`, in order.

## Task Commits

Tasks 1 and 2 were committed together (see Deviations): `3590f2e6b` fix(81-13): gate checks every playbook step and compensation step.

## Metrics

- gate.py: 496 lines before, 498 after (cap 500). dispatch_check.py: 107 lines.
- autonomous_remediation_service.py: +13 / -3 (net +10 lines, under the 30-line limit).
- New tests: 20 in test_autonomous_ops_dispatch_binding.py (real throwaway Mongo).
- Existing tests changed: none.

## Verification

- Plan verify command 1 (dispatch_binding, gate, gate_order, registry, structural, xdr_fence): 98 passed, 0 skipped.
- Plan verify command 2 (`-k "autonomous_ops or remediation or ueba or rotate_key"` over backend/tests): 471 passed.
- `test_vendored_block_ip_playbook_stays_automatic_through_decide`, the six `test_only_registry_actions_reach_the_queue` cases and the oracle test pass.

## Deviations from Plan

### Auto-fixed Issues

None - plan executed as written, with one process deviation:

**1. [Process] Tasks 1 and 2 share one commit.** `classify` (Task 2) replaced `_step_class` in the same edit that wired `spec_pairs` (Task 1), and the tracer test module covers both; the two could not be split into separate green commits without a throwaway intermediate state. Both tasks' verify commands were run against the final state.

## Known Stubs

None.

## Threat Flags

None. T-81-50 and T-81-51 are mitigated by this plan (regression tests with the protected IP in each position and for each malformed class case).

## Notes for later plans

- 81-15 binds execution to the recorded `steps`; 81-18 re-checks every recorded step at approval and makes `approvals.undo` return `no_undo` for multi-step rows.
- GATE-03, GATE-08, GATE-10, ACTV-01 stay pending in REQUIREMENTS.md because 81-15/16/17/18 still list them; only GATE-04 was marked complete.
- Steps for the user: none (no restart, migration or live-database action in this plan; the backend runs from this checkout and picks the change up on its next restart).

## Self-Check: PASSED

- backend/autonomous_ops/dispatch_check.py, backend/tests/test_autonomous_ops_dispatch_binding.py: present.
- Commit 3590f2e6b: present in HEAD history.
