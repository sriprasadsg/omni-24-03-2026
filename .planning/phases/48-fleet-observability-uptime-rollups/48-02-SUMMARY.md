---
phase: 48-fleet-observability-uptime-rollups
plan: 02
subsystem: infra
tags: [background-jobs, mongodb, retention, uptime, fastapi, asyncio]

requires:
  - phase: 48-01
    provides: agent_uptime_service.compute_uptime (heartbeat-presence uptime %) reused verbatim for the daily rollup value
provides:
  - "agent_uptime_rollup_loop() daily background sweep writing one BSON-Date-timestamped row per agent per day into agent_uptime_rollups"
  - "RetentionService.cleanup_agent_uptime_rollups() wired into run_cleanup() (90-day default)"
  - "agent_uptime_rollups collection scaffolding for a future longer-range (7d/30d) uptime UI (deferred this phase per D-02)"
affects: [49-fleet-geo-map, future-longer-range-uptime-ui]

tech-stack:
  added: []
  patterns:
    - "Daily background sweep cloned from snapshot_compliance_scores_loop: raw db._db cross-tenant iteration, set_tenant_id/reset_tenant_id per tenant, try/except/finally shape"
    - "Single-pass sweep body factored into a separate testable function (_run_agent_uptime_rollup_once) rather than testing the infinite while loop directly"
    - "Retention cleanup methods cloned from cleanup_agent_location_history: native BSON Date $lt cutoff, platform-wide delete_many, no tenantId filter"

key-files:
  created:
    - backend/tests/test_agent_uptime_rollup_loop.py
  modified:
    - backend/app_background_tasks.py
    - backend/app_startup.py
    - backend/retention_service.py
    - backend/tests/test_retention_agent_location_history.py

key-decisions:
  - "agent_uptime_rollups rows store timestamp as datetime.now(timezone.utc) (native BSON Date), never .isoformat() — required so retention's $lt comparison works correctly (Pattern 3 / T-48-06)"
  - "Sweep window for the daily % is a fixed 24h lookback per agent, reusing compute_uptime(rows, 24) unchanged from 48-01 — no new uptime math introduced"
  - "No historical backfill on first run (D-08): agent_uptime_rollups is expected to be empty immediately after deploy and fill in one row per agent per day going forward"
  - "retention_endpoints.py's _POLICY_DEFAULTS admin-configurable policy list was intentionally NOT extended to include agent_uptime_rollups — out of this plan's declared files_modified scope; run_cleanup's own 90-day default still applies correctly without it"

patterns-established:
  - "Pattern: any new cross-tenant daily rollup sweep clones snapshot_compliance_scores_loop's raw-db tenant-iteration shape rather than reinventing it"
  - "Pattern: any new retention-eligible collection with a native-datetime timestamp field clones cleanup_agent_location_history's $lt delete_many shape"

requirements-completed: [FOBS-02]

coverage:
  - id: D1
    description: "agent_uptime_rollup_loop() daily sweep writes one row per agent per day into agent_uptime_rollups, keyed on {agent_id, date}, with tenant_id and a native BSON Date timestamp"
    requirement: "FOBS-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_agent_uptime_rollup_loop.py::TestAgentUptimeRollupSweep::test_one_upsert_per_agent_across_all_tenants"
        status: pass
      - kind: unit
        ref: "backend/tests/test_agent_uptime_rollup_loop.py::TestAgentUptimeRollupSweep::test_upsert_keyed_on_agent_id_and_date_with_tenant_id_set"
        status: pass
      - kind: unit
        ref: "backend/tests/test_agent_uptime_rollup_loop.py::TestAgentUptimeRollupSweep::test_upsert_timestamp_is_native_datetime_not_isoformat_string"
        status: pass
      - kind: unit
        ref: "backend/tests/test_agent_uptime_rollup_loop.py::TestAgentUptimeRollupSweep::test_reads_go_through_raw_db_underscore_db"
        status: pass
    human_judgment: false
  - id: D2
    description: "agent_uptime_rollup_loop is registered in app_startup.py's background-task startup block alongside the other daily sweeps"
    requirement: "FOBS-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_agent_uptime_rollup_loop.py::TestAgentUptimeRollupSweep::test_loop_function_exists_and_is_registered_by_name"
        status: pass
      - kind: other
        ref: "backend/venv/bin/python -c \"import app_background_tasks, app_startup\" (exit 0)"
        status: pass
    human_judgment: false
  - id: D3
    description: "retention_service.run_cleanup() deletes agent_uptime_rollups rows older than the configured retention_days (default 90) and reports the count; agent_metrics retention deliberately untouched"
    requirement: "FOBS-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_agent_uptime_rollup_loop.py::TestCleanupAgentUptimeRollups::test_90_day_old_row_deleted_1_day_old_row_retained"
        status: pass
      - kind: unit
        ref: "backend/tests/test_agent_uptime_rollup_loop.py::TestRunCleanupWiringForUptimeRollups::test_run_cleanup_report_includes_agent_uptime_rollups_deleted_key"
        status: pass
      - kind: unit
        ref: "backend/tests/test_agent_uptime_rollup_loop.py::TestRunCleanupWiringForUptimeRollups::test_run_cleanup_does_not_add_agent_metrics_retention"
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-07-29
status: complete
---

# Phase 48 Plan 02: Daily Uptime Rollup Sweep + Retention Wiring Summary

**Daily `agent_uptime_rollup_loop()` background sweep writes per-agent uptime % (BSON-Date timestamped, no backfill) into a new `agent_uptime_rollups` collection by reusing 48-01's `compute_uptime`, with `retention_service.run_cleanup()` now pruning it at a 90-day default.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-07-29T18:05:04Z (approx.)
- **Completed:** 2026-07-29T18:04:51+00:00 (last commit)
- **Tasks:** 2/2 completed
- **Files modified:** 5 (2 new/edited production files, 1 startup wiring edit, 2 test files)

## Accomplishments
- `agent_uptime_rollup_loop()` added to `backend/app_background_tasks.py`, cloning `snapshot_compliance_scores_loop`'s raw `db._db` cross-tenant iteration shape and reusing `agent_uptime_service.compute_uptime` for the daily % — no duplicated uptime math.
- Single-pass sweep body factored into `_run_agent_uptime_rollup_once(db)` so the write shape is testable without driving the infinite `while True: await asyncio.sleep(86400)` loop.
- Upserts one row per agent per day into `agent_uptime_rollups`, keyed on `{agent_id, date}`, with an explicit `tenant_id` on every row (T-48-04) and a native BSON Date `timestamp` (never `.isoformat()`, per Pattern 3 / T-48-06).
- No historical backfill on first run (D-08) — documented in the function's own docstring so an empty collection immediately post-deploy isn't mistaken for a bug.
- Loop registered in `backend/app_startup.py` alongside the other daily background sweeps (`monitor_agent_status`, `refresh_mitre_heatmap_loop`, `compliance_evidence_sweep_loop`, `snapshot_compliance_scores_loop`).
- `RetentionService.cleanup_agent_uptime_rollups()` added to `backend/retention_service.py`, cloning `cleanup_agent_location_history`'s native-datetime `$lt` `delete_many` (Phase 46 precedent), default 90-day retention, platform-wide (no tenantId filter).
- Wired into `run_cleanup()`: report dict now includes `agent_uptime_rollups_deleted`. `agent_metrics` retention deliberately NOT added (Pitfall 4 / D-02 out of scope).
- 11 hermetic unit tests added in `backend/tests/test_agent_uptime_rollup_loop.py` covering both the sweep write shape and the retention delete/wiring.

## Task Commits

Each task was committed atomically:

1. **Task 1: agent_uptime_rollup_loop daily sweep + startup registration** - `aaa053e` (feat)
2. **Task 2: agent_uptime_rollups retention wiring** - `425da17` (feat)

**Plan metadata:** (this commit, following SUMMARY/self-check)

## Files Created/Modified
- `backend/app_background_tasks.py` - Added `agent_uptime_rollup_loop()` and its factored single-pass helper `_run_agent_uptime_rollup_once(db)`
- `backend/app_startup.py` - Imported and registered `agent_uptime_rollup_loop` via `_safe_bg_task`
- `backend/retention_service.py` - Added `cleanup_agent_uptime_rollups()`, wired into `run_cleanup()`
- `backend/tests/test_agent_uptime_rollup_loop.py` - New hermetic test file (11 tests: sweep write shape + retention delete/wiring)
- `backend/tests/test_retention_agent_location_history.py` - Rule 1 fix: added `agent_uptime_rollups` to the mocked-collection loop in `_make_db` (see Deviations)

## Decisions Made
- Fixed 24h lookback window per agent for the daily rollup's `compute_uptime(rows, 24)` call — matches the existing `agent_metrics` cadence assumption, no new tunable introduced.
- `agent_uptime_rollups` timestamp stored via `datetime.now(timezone.utc)` (native BSON Date) rather than `.isoformat()`, matching the `agent_location_history` convention exactly so retention's `$lt` comparison is correct from day one.
- Did not extend `retention_endpoints.py`'s `_POLICY_DEFAULTS` to include `agent_uptime_rollups` (Phase 46 did this for `agent_location_history`) — this plan's `files_modified` frontmatter explicitly locked scope to 4 files, and `run_cleanup`'s own `p.get("agent_uptime_rollups", 90)` default already produces correct behavior without an admin-configurable policy row. Flagged here rather than silently expanding scope.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed a pre-existing test regression caused directly by this plan's `run_cleanup()` change**
- **Found during:** Task 2 (retention wiring) — full-suite verification after adding `cleanup_agent_uptime_rollups` to `run_cleanup`
- **Issue:** `test_retention_agent_location_history.py`'s `_make_db()` helper only mocked `("audit_logs", "metrics", "notifications")` collections. Once `run_cleanup()` started calling `self.db.agent_uptime_rollups.delete_many(...)`, 2 of that file's existing tests failed with `TypeError: object MagicMock can't be used in 'await' expression` because `agent_uptime_rollups` was an un-configured plain `MagicMock` attribute rather than an `AsyncMock`-backed collection.
- **Fix:** Added `"agent_uptime_rollups"` to the tuple of collection names `_make_db()` mocks with `AsyncMock(return_value=_DeleteResult(0))`.
- **Files modified:** `backend/tests/test_retention_agent_location_history.py`
- **Verification:** `backend/venv/bin/python -m pytest tests/test_agent_uptime_rollup_loop.py tests/test_retention_agent_location_history.py -q` → 15 passed.
- **Committed in:** `425da17` (part of Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 Rule 1 bug)
**Impact on plan:** Fix was a direct, necessary consequence of this plan's own `run_cleanup()` change to an existing test's fixture setup — no scope creep, no behavior change to production code.

## Issues Encountered
None beyond the deviation above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `agent_uptime_rollups` collection now accumulates one row per agent per day going forward — the scaffolding a future longer-range (7d/30d) uptime UI would read from is in place, with zero UI built this phase (per D-02).
- `run_cleanup()` now prunes `agent_uptime_rollups` at the same cadence as the other retention-eligible collections; no unbounded growth risk (T-48-05 mitigated).
- Full backend suite re-verified: 1442 passed / 34 skipped / 8 failed — all 8 failures confirmed pre-existing and unrelated (no import dependency on any of this plan's 4 changed files; reproduce identically in isolation): `test_webhook_logic.py` (2), `test_support_admin_to_user.py` (3, asyncio event-loop API deprecation under Python 3.12), plus the 3 previously-documented pre-existing failures (`test_agentic_ai.py` tool_choice, `test_e2e_integration.py` golden path, `test_rust_heartbeat_parity.py`).
- No blockers for Phase 48's remaining plans (FOBS-01/03 frontend/endpoint work) or Phase 49 (Fleet Geo Map).

---
*Phase: 48-fleet-observability-uptime-rollups*
*Completed: 2026-07-29*

## Self-Check: PASSED

All created/modified files confirmed present on disk; both task commits (`aaa053e`, `425da17`) confirmed in git log.
