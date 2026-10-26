---
phase: 81-autonomy-gate-stop-switch-activity-ledger
plan: 16
subsystem: autonomous-ops
tags: [remediation, tenant-isolation, rollback, circuit-breaker, pytest, gap-closure]

requires:
  - phase: 81-autonomy-gate-stop-switch-activity-ledger (81-13)
    provides: rows carry steps and rollback
  - phase: 81-autonomy-gate-stop-switch-activity-ledger (81-14)
    provides: messages.REASON_TEXT pattern, breaker-aware settings
provides:
  - "remediation_playbook_service.load_playbooks(db, tenant_id) and _belongs(playbook, tenant_id): selection sees only vendored defaults plus the finding's own tenant"
  - "rolled_back only when every compensation step returned SUCCESS; otherwise failed rollback_incomplete with escalation"
  - "AutonomousRemediationService._escalate and _evaluate_breaker helpers"
  - "messages.REASON_TEXT['rollback_incomplete']"
affects: [81-17, 81-18]

actuals:
  tokens: 30000
  tasks: 2
  commits: 2

plan_head_before: cf27d6fdfee7eddbab8522a9952fd8dfd31a6d26
plan_head_after: 8e70012c8e11b314485cfb605306477276d4404c
commits: 2

tech-stack:
  added: []
  patterns:
    - "Tenant-scoped selection: untenanted vendored defaults first, then the tenant's own documents; later wins by name"
    - "Truthful terminal state: a host-confirmed result decides the row state, never the intention to compensate"

key-files:
  created:
    - backend/tests/test_autonomous_ops_remediation_truth.py
  modified:
    - backend/remediation_playbook_service.py
    - backend/autonomous_remediation_service.py
    - backend/autonomous_ops/messages.py

key-decisions:
  - "Escalation helper is AutonomousRemediationService._escalate(db, base_record, finding, playbook, result, what); the single REMEDIATION_ESCALATION alert text is shared by the no-rollback and incomplete-rollback branches."
  - "Automatic (not person-approved) outcomes are not detected in the service: breaker.evaluate is called after every failed or rolled_back outcome and itself counts only autoDispatched rows (ledger.recent_finished_auto), so an approved card never trips the breaker (D-18 unchanged)."
  - "A tenant's own stamped copy of a vendored playbook (same tenantId) is still selectable for that tenant, preserving the within-tenant override feature; another tenant's stamped copy never is."

requirements-completed: [GATE-07, GATE-11, GATE-14]

duration: 40min
completed: 2026-10-26
status: complete
---

# Phase 81 Plan 16: Tenant-scoped playbooks and truthful undo Summary

**A tenant-B finding can no longer select tenant A's operator playbook, and a compensation that timed out, failed or was refused now leaves the row Failed (rollback_incomplete) with a human-review alert instead of "Undone."**

## Accomplishments

- Task 1 (tracer): `load_playbooks(db, tenant_id)` returns the vendored defaults read from disk followed by documents whose `tenantId` equals the finding's tenant. `select_playbook` additionally filters through `_belongs` (untenanted vendored defaults, or the finding's own non-empty tenant id), so even a caller-supplied mixed list cannot leak: a vendored copy stamped and edited by tenant A, and any non-vendored document without a tenant id, are never selected. End to end, `remediate()` of a tenant-B shadow_ai anomaly with tenant A's two-step kill_process in the collection records a one-step row.
- Task 2: in the verify-failed branch every compensation step is attempted, the `rollback_dispatched` audit stage carries `complete`, and the row moves failed -> rolled_back only when all steps returned SUCCESS. Otherwise failed -> failed with reasonCode `rollback_incomplete`, result `rollback_dispatched False` and `escalated True`, one REMEDIATION_ESCALATION alert and an `escalated` audit stage. The ledger mirror shows `verify_failed` before `rollback_incomplete`. The empty-rollback path is unchanged (still `verify_failed` plus escalation).
- `breaker.evaluate` now runs after a failed or rolled_back outcome and after an unconfirmed dispatch (`dispatch_failed`), failure-isolated; three incomplete rollbacks in a row trip the tenant's breaker to suggest without the reconciler.
- Service growth: `autonomous_remediation_service.py` 881 -> 903 lines (net +22, under the 40 cap). `remediation_playbook_service.py` 163 -> 180.

## Task Commits

1. Task 1 (tracer): `f8417c21b` fix(81-16): playbook selection is tenant-scoped; another tenant's steps are never selected
2. Task 2: `8e70012c8` fix(81-16): Undone only when every compensation step was confirmed; breaker sees remediation outcomes

## Verification

- Task 1 command (truth, remediation_playbook, rotate_key_wiring, structural, remediation_guards, ueba_remediation_trigger): 90 passed, 0 skipped.
- Task 2 command (truth, remediation_guards, copy, gate, breaker, remediation_loop): 108 passed, 0 skipped. `npx vitest run src/__tests__/autonomousOpsCopy.test.ts`: 18 passed.
- Whole `backend/tests/test_autonomous_ops_*.py`: 397 passed, 0 failed, 0 skipped.
- `backend/tests -k "remediation or ueba or rotate_key or playbook or xdr"`: 170 passed, 0 failed.
- Acceptance greps: `"rollback_incomplete"` in messages.py 1; `rollback_incomplete` in the service 2; `breaker.evaluate(` 1; `REMEDIATION_ESCALATION` 1; `def _belongs` 1; `load_playbooks(db, tenant_id)` 1.

## Deviations from Plan

None - plan executed as written. The escalation alert text for the no-rollback case now reads "Remediation '<name>' ... failed verification and has no rollback" (the word "Irreversible" was dropped to share one helper across both branches); no test or UI string depended on it.

## Tests

New module `backend/tests/test_autonomous_ops_remediation_truth.py` (20 tests, real throwaway Mongo, local stand-in agent, no live system): hermetic cross-tenant selection cases, `_belongs`, `load_playbooks` against Mongo, end-to-end remediate(), TIMEOUT / FAILURE / refused / mixed SUCCESS+TIMEOUT / all-SUCCESS compensation, audit ordering, breaker trip after three, breaker raising, unconfirmed dispatch evaluation. The dry-run overrides use both the environment variable and a `create=True` patch of the module constant, so they hold before and after 81-17.

## Known Stubs

None.

## Threat Flags

None. T-81-59, T-81-60 and T-81-61 are mitigated and covered by tests.

## Notes for later plans / steps for the user

- Requirements GATE-07, GATE-11 and GATE-14 marked complete. GATE-08 and ACTV-01 stay pending: 81-18 still lists them.
- `load_playbooks` now requires a tenant id; its only caller is `_remediate`.
- No restart, migration or live-database action was taken; the backend picks the change up on its next restart.

## Self-Check: PASSED

- backend/tests/test_autonomous_ops_remediation_truth.py, backend/remediation_playbook_service.py (`def _belongs`): present.
- Commits f8417c21b and 8e70012c8: present in HEAD history.
