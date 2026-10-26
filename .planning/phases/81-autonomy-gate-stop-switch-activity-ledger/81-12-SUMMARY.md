---
phase: 81-autonomy-gate-stop-switch-activity-ledger
plan: 12
subsystem: autonomous-ops
tags: [migration, tenant-settings, indexes, sign-up, mongo, pytest]

requires:
  - phase: 81-autonomy-gate-stop-switch-activity-ledger (81-01)
    provides: settings.ensure_tenant / ensure_indexes, ledger.ensure_indexes
  - phase: 81-autonomy-gate-stop-switch-activity-ledger (81-11)
    provides: protected.ensure_indexes
provides:
  - "migration 024: explicit autonomy_settings document for every tenant with an id (platform-admin stored off/off), plus every autonomy index and the stamp partial indexes"
  - "settings.ensure_tenant at sign-up and Add Tenant, failure tolerated"
affects: [81-08, 81-09]

actuals:
  tokens: 9500
  tasks: 2
  commits: 2

plan_head_before: d8b3312c0dd21451cd5e7cc221b0763ed97bbfd3
plan_head_after: cdf9510e0c16686e39cf89ce04c23616ffc4a735
commits: 2

tech-stack:
  added: []
  patterns:
    - "Migration delegates to the owning modules' ensure_* functions instead of repeating index definitions"
    - "Best-effort hook after tenant creation: try/except with a logged warning, startup ensure_all_tenants is the backstop"

key-files:
  created:
    - backend/migrations/024_autonomous_ops.py
    - backend/tests/test_autonomous_ops_migration.py
  modified:
    - backend/authentication_endpoints.py
    - backend/tenant_endpoints.py

key-decisions:
  - "The sign-up hook runs after the admin user insert, not directly after the tenants insert: a duplicate-email rollback deletes the tenant, and a hook placed earlier would leave an orphan autonomy_settings row"
  - "Migration indexes come only from settings.ensure_indexes, ledger.ensure_indexes (includes open_dedupe and state_expiry) and protected.ensure_indexes; only the two stamp indexes are defined in the migration"
  - "Stamp index is named autonomy_stamp on (autonomy.tenantId, status) with partialFilterExpression autonomy.actionId exists, on agent_instructions and response_tasks"

requirements-completed: [GATE-01]

duration: 6min
completed: 2026-10-26
status: complete
---

# Phase 81 Plan 12: Migration 024 and the new-tenant default Summary

**Migration 024 gives every existing tenant an explicit stored autonomy level (platform-admin off/off) idempotently with all autonomy indexes, and sign-up and Add Tenant now write the same default for new tenants without ever blocking creation**

## Accomplishments

- `up(db)` walks tenants, skips documents without an id, calls `settings.ensure_tenant` ($setOnInsert upsert), then creates the settings, ledger and never-touch indexes through their owners and the two stamp partial indexes. Second run changes nothing; a stored `suggest` level survives; result is independent of tenant order.
- Sign-up and Add Tenant call `ensure_tenant` in a try/except that logs a warning. Tests prove the default document is written, the call receives the new tenant id, and a raising `ensure_tenant` still leaves the tenant created.

## Documents written on the throwaway database

Tenants `platform-admin`, `t-a`, `t-b` plus one id-less tenant produced exactly three `autonomy_settings` documents: `platform-admin` level off / maxLevel off, `t-a` and `t-b` undoable_auto / undoable_auto, all with shadow true, stop null, breaker null. Add Tenant and sign-up each produced undoable_auto / undoable_auto / shadow true for the new tenant id.

## Indexes created by up()

- `autonomy_settings`: `tenant_unique` (tenantId, unique)
- `autonomy_actions`: `id_unique`, `tenant_created`, `tenant_state_created`, `state_expiry`, `open_dedupe` (unique, partial on open states with a string dedupeKey)
- `autonomy_never_touch`: `id_unique`, `entry_unique`
- `agent_instructions` and `response_tasks`: `autonomy_stamp` (autonomy.tenantId, status; partial on autonomy.actionId exists)

## Task Commits

1. **Task 1 (tracer): migration 024 and its tests** - `e0ce5322c` (feat)
2. **Task 2: creation hooks and hook tests** - `cdf9510e0` (feat)

## Deviations from Plan

**1. [Plan detail not met] `updatedBy` is `system`, not `migration-024`**
- The plan's behavior line says documents carry `updatedBy migration-024`. `settings.ensure_tenant` (81-01, not to be edited by this plan) writes `updatedBy: "system"`, so the migration documents carry that value. Nothing reads it for behavior; the tests do not assert it.

**2. [Placement] Sign-up hook sits after the user insert** (see key-decisions). It is still immediately after the tenant creation succeeds.

No Rule 1-4 fixes were needed.

## User-owned changes

`backend/authentication_endpoints.py` (MFA exemption hunks) and `backend/tenant_endpoints.py` (agentCollectionIntervals hunks) were staged through `stage-own.sh`; `git diff --cached` showed only the 8-line hook per file, and `git diff --stat` afterwards still shows the user's hunks unstaged and uncommitted in both files. The committed hooks reference no `mfa_exempt` or `agentCollectionIntervals`.

## Verification

`backend/venv/bin/python -m pytest tests/test_autonomous_ops_migration.py tests/test_database_migrations_lock.py tests/test_tenant_signup_approval.py` - 22 passed, none skipped (real Mongo reachable on this VM; tests use throwaway `omni_test_*` databases only).

## User steps (live, not done here)

- Migration 024 runs at the next backend restart (`run_migrations`). Not run against the live database by this plan. After it: every tenant should hold an `autonomy_settings` document and `platform-admin` should be off/off (GATE-01 live check, assumption A-81-LIVE-MIGRATION).

## Known Stubs

None.

## Threat Flags

None. The two hooks write only to `autonomy_settings` for the tenant just created.

## Self-Check: PASSED

- backend/migrations/024_autonomous_ops.py and backend/tests/test_autonomous_ops_migration.py exist.
- Commits e0ce5322c and cdf9510e0 are ancestors of HEAD.
