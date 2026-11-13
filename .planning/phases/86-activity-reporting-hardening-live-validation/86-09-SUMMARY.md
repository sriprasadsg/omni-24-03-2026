---
phase: 86-activity-reporting-hardening-live-validation
plan: 09
subsystem: autonomous-ops-reporting
tags: [migration, mongodb-indexes, two-tenant, tenant-isolation, digest, export, statistics, pytest, autonomous-ops]
status: complete

requires:
  - phase: 86-03
    provides: two-tenant test file and the assert_no_crossing helper
  - phase: 86-05
    provides: digest.ensure_indexes, the autonomy_digests claim collection
  - phase: 86-06
    provides: export.build
  - phase: 86-07
    provides: golive.ensure_indexes, autonomy_golive_checks
provides:
  - Migration 035 (indexes only): digest_once_per_day (unique), tenant_finished, check_recorded, id_unique
  - Two-tenant proof for statistics, export and the daily digest (D-17)
affects: [86-13]

actuals:
  tokens: 5000
  tasks: 2
  commits: 3
plan_head_before: 432a5b68c34c158d5aa8b595296b303f72b44887
plan_head_after: b4b4912f0a0fa6677e825e57fa9f65f05007b413

tech-stack:
  added: []
  patterns:
    - migration calls the modules' own ensure_indexes, so one definition of each index serves the migration and the self-healing loops
    - reporting two-tenant cases reuse assert_no_crossing and the per-tenant seeding of the loop cases

key-files:
  created:
    - backend/migrations/035_activity_reporting.py
    - backend/tests/test_migration_035_activity_reporting.py
  modified:
    - backend/tests/test_autonomous_ops_two_tenant.py

key-decisions:
  - "Migration 035 imports digest and golive lazily inside up() and creates no index of its own, so it cannot drift from the loops and does not depend on anything migration 034 creates."
  - "The runner-record test patches discovery down to 035 and runs the real run_migrations on the private database, rather than inserting the _migrations record by hand."

requirements-completed: []

coverage:
  - id: D1
    description: "Migration 035 creates the four Phase 86 indexes, digest_once_per_day is unique, and a second run changes no index, no document and no seeded decision row"
    requirement: ACTV-04
    verification:
      - kind: unit
        ref: "backend/tests/test_migration_035_activity_reporting.py#test_a_second_run_changes_no_index_and_no_document_and_a_seeded_row_is_untouched"
        status: pass
      - kind: unit
        ref: "backend/tests/test_migration_035_activity_reporting.py#test_the_digest_claim_index_is_unique_per_tenant_and_day"
        status: pass
  - id: D2
    description: "The runner discovers 035 right after 034 and records it in _migrations"
    requirement: ACTV-04
    verification:
      - kind: unit
        ref: "backend/tests/test_migration_035_activity_reporting.py#test_the_runner_discovers_035_after_034"
        status: pass
      - kind: unit
        ref: "backend/tests/test_migration_035_activity_reporting.py#test_the_runner_applies_035_and_records_it_in_the_migrations_collection"
        status: pass
  - id: D3
    description: "Statistics, export and the digest do not cross tenants over same-shaped rows (GATE-11 / D-17)"
    requirement: GATE-11
    verification:
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_two_tenant.py#test_statistics_for_each_tenant_total_only_its_own_rows"
        status: pass
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_two_tenant.py#test_the_export_of_each_tenant_holds_its_own_targets_and_shares_only_the_platform_stop_row"
        status: pass
      - kind: unit
        ref: "backend/tests/test_autonomous_ops_two_tenant.py#test_the_digest_stores_one_notice_and_one_claim_per_tenant_each_naming_only_its_own_items"
        status: pass
---

# Phase 86 Plan 09: Migration 035 and reporting two-tenant cases Summary

Migration 035 creates the Phase 86 indexes (indexes only, via the digest and go-live `ensure_indexes`), and statistics, export and the daily digest each now carry a two-tenant proof on the private mongod.

## TDD

- **RED** (81d99ab09): `test_migration_035_activity_reporting.py` with five cases. Run before the migration existed on the private mongod: all 5 failed, the four DB cases on `ModuleNotFoundError: No module named 'migrations.035_activity_reporting'` and the runner cases on the assertion that `035_activity_reporting` is in the discovered list (and that a `_migrations` record exists). Semantic assessment: the target tests ran and failed because the migration is absent, the planned reason; no fixture or collection fault. The machine classifier (`check tdd-red-evidence`) was not run because pytest output is not one of its supported report formats.
- **GREEN** (546e15d03): `035_activity_reporting.py` calls `digest.ensure_indexes` and `golive.ensure_indexes`. One test-side fix: Mongo returns naive datetimes, so the untouched-row comparison re-attaches UTC before comparing.
- **REFACTOR**: none.
- Task 2 is a tests-only task (plan `type="auto"` without `tdd`); the new cases pass against existing code and are one commit (b4b4912f0).

## Verification

- Task 1 command: 23 passed, 0 skipped (`test_migration_035_activity_reporting.py`, `test_autonomous_ops_migration.py`, `test_database_migrations_lock.py`), all on 127.0.0.1:27998.
- Task 2 command: 7 passed, 0 skipped (`test_autonomous_ops_two_tenant.py`).
- Acceptance: migration has 0 write verbs and 4 `ensure_indexes` mentions; two-tenant file has 7 `def test_`, 3 reporting-surface mentions and 388 lines.

## Deviations from Plan

None. The plan executed as written. One small addition: the two-tenant file's docstring `no_claim` line, which said 86-09 would add the reporting cases, now states they exist.

## Notes

- Migration 035 was never run against the live database; it applies at the user's restart (86-13).
- `requirements-completed` is left empty: ACTV-04, ACTV-05 and ACTV-06 still read Pending in REQUIREMENTS.md after 86-08 and the UI plans (86-10..12) are not done, so the requirements were not marked here; GATE-11 is already Complete.

## Known Stubs

None.

## Threat Flags

None. No new endpoint, auth path or schema change; three index definitions and tests only (T-86-24 accepted, T-86-25 mitigated by the new cases).

## Self-Check: PASSED

Files found: backend/migrations/035_activity_reporting.py, backend/tests/test_migration_035_activity_reporting.py, backend/tests/test_autonomous_ops_two_tenant.py. Commits 81d99ab09, 546e15d03 and b4b4912f0 are reachable from HEAD.
