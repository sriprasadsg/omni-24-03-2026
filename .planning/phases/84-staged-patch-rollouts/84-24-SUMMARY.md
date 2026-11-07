---
phase: 84-staged-patch-rollouts
plan: 24
subsystem: patching
status: complete
tags: [patch-rollout, rollback, gap-closure, wr-10, python]

requires:
  - phase: 84-staged-patch-rollouts
    provides: rolloutId stamped on rollout install jobs (installs.py) and revert jobs (revert.py)
provides:
  - rollback_patch_job refuses any job carrying rolloutId with 409 and a pointer to Rollouts, before any insert
  - ROLLOUT_OWNED_JOB_DETAIL, the one sentence constant in backend/patch_core_endpoints.py
  - 4 tests in test_patch_rollout_legacy_fence.py (A rollout install job, B rollout revert job, C ordinary job unchanged, D other tenant not disclosed)
affects: [84-25, 84-27]

requirements-completed: [PTCH-04, PTCH-06]

actuals:
  tokens: 3200
  tasks: 2
  commits: 3
commits: 3
plan_head_before: 244b846f15303be4017fa630759e9fd1ccc90286
plan_head_after: eb0a78877ea43d39ba967d41d6f9fec53e576bd8

tech-stack:
  added: []
  patterns: [tenant check first, then ownership refusal, so another tenant learns nothing about rolloutId]

key-files:
  created: []
  modified:
    - backend/patch_core_endpoints.py
    - backend/tests/test_patch_rollout_legacy_fence.py

key-decisions:
  - "The refusal sits after the 404 tenant check and before the status check and every instruction insert (T-84-68)."

duration: 10 min
completed: 2026-11-07
---

# Phase 84 Plan 24: Manual rollback refuses rollout jobs Summary

WR-10 closed: POST /api/patches/deployment-jobs/{id}/rollback answers 409 "This job belongs to a rollout. Revert it from Rollouts on the Patching screen." for any job with rolloutId, and queues nothing, so a rollout's jobs are reverted only through the rollout gate.

## Accomplishments

- `rollback_patch_job` raises 409 with `ROLLOUT_OWNED_JOB_DETAIL` when `job.get("rolloutId")` is set. The tenant check stays first, so a caller from another tenant still gets the 404 and learns nothing.
- Tests A and B (rollout install job, rollout revert job) were written first and failed with "DID NOT RAISE" before the fix. Tests C and D (ordinary job still queues its `rollback_patches` instruction; other tenant's rollout job answers 404) pass before and after, by design.
- UI check (plan asked to confirm by grep): `components/PatchDeploymentJobs.tsx` handleRollback shows `error.error` on a non-OK response, and `backend/error_handlers.py` http_exception_handler returns `{"error": <detail>}`. So the server sentence reaches the user's toast. No UI change.
- The sentence has no banned-term violation (checked with `violations()` and `load_rules()` from test_patch_rollout_messages.py; the copy gate test only scans the messages module, so the check was run on this string directly).

## Verification

- Fence + messages + endpoints suites: 49 passed on a private mongod (port 27997). Fence + test_patch_deployment_flow (existing rollback tests): 35 passed. Private mongods stopped afterwards.

## Task Commits

1. Task 1 (tracer), RED: 42e9b00a5 test(84-24) tests A and B
2. Task 1 (tracer), GREEN: ca8a7fa74 fix(84-24) route refusal
3. Task 2: eb0a78877 test(84-24) tests C and D

Tracer gate: verify re-run end to end after the fix (passed), then expanded.

## Deviations from Plan

None in behaviour. One wording note: Task 1's acceptance criterion says the grep for "This job belongs to a rollout" returns one match "inside rollback_patch_job"; the plan's artifact section asks for a module-level constant, so the string lives in the constant `ROLLOUT_OWNED_JOB_DETAIL` (line 254) and the function uses the constant. Still one match for the sentence. Tests C and D had no RED phase because they pin unchanged behaviour.

## Threat Flags

None. T-84-68 mitigated (tests A, B, D).

## Known Stubs

None.

## Self-Check: PASSED

- backend/patch_core_endpoints.py and backend/tests/test_patch_rollout_legacy_fence.py exist and carry the changes.
- Commits 42e9b00a5, ca8a7fa74, eb0a78877 are ancestors of HEAD; `git rev-list --count` from the ledger base = 3.
