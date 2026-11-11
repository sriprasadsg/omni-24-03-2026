---
phase: 86-activity-reporting-hardening-live-validation
plan: 01
subsystem: autonomous-ops-reporting
tags: [fastapi, mongodb-aggregation, react, vitest, pytest, autonomous-ops, statistics]
status: complete

requires:
  - phase: 81-autonomous-ops-safety-core
    provides: autonomy_actions decision ledger, catalogue guard, views.resolve_tenant
provides:
  - backend/autonomous_ops/reporting package (every Phase 86 constant, stats, plain rule names)
  - GET /api/autonomous-ops/statistics (per-rule counts, simulation kept apart, time-saved estimate)
  - collapsed Statistics card on the Autonomous Ops screen (tenant scope)
  - ACTV-08 copy gate registration of the new files and folders (JSON, pytest, vitest)
affects: [86-02, 86-03, 86-04, 86-05, 86-06, 86-07, 86-08, 86-09, 86-10, 86-11, 86-12, 86-13]

actuals:
  tokens: 11533
  tasks: 3
  commits: 5
plan_head_before: 86312d3ef77e358d14ca3c82a32102d5b5462381
plan_head_after: fb6e8dd7f8322bff106e3c10342ffa87e3d53a62

tech-stack:
  added: []
  patterns:
    - one tenant-scoped $group aggregation folded in Python (compute / fold / time_saved)
    - code-owned read-only tables (MappingProxyType) for minutes per kind and rule names
    - StatsCard owns no period state; the screen owns statsDays for the later Export dialog

key-files:
  created:
    - backend/autonomous_ops/reporting/__init__.py
    - backend/autonomous_ops/reporting/stats.py
    - backend/autonomous_ops/reporting/rule_names.py
    - backend/autonomous_ops_reporting_endpoints.py
    - backend/tests/test_autonomous_ops_stats.py
    - services/autonomousOpsReporting.ts
    - components/autonomousOpsStats/StatsCard.tsx
    - components/autonomousOpsStats/reportingCopy.ts
    - src/__tests__/autonomousOpsStats.test.tsx
  modified:
    - backend/catalogue_mounts_autonomous_ops.py
    - backend/router_registry.py
    - backend/tests/test_catalogue_slice_autonomous_ops.py
    - components/AutonomousOpsActivity.tsx
    - shared/autonomous-ops-banned-terms.json
    - backend/tests/test_autonomous_ops_copy.py
    - src/__tests__/autonomousOpsCopy.test.ts

key-decisions:
  - "Refused counts refused, expired and cancelled_by_stop; denied stays its own column and is excluded from approved even though approvals.deny records the approver (D-07, A-86-A2)."
  - "Period edge: createdAt >= now - days. BSON stores milliseconds, so the 'one microsecond earlier' row is stored a millisecond earlier and is excluded."
  - "The reporting router is loaded by router_registry but not added to _REQUIRED_ROUTERS, so losing it only degrades reporting."

requirements-completed: [ACTV-05, ACTV-07]

duration: ~20min
completed: 2026-11-11
---

# Phase 86 Plan 01: Statistics tracer and column semantics Summary

**A tenant admin's Autonomous Ops screen now shows a collapsed Statistics card ("Last 30 days · 2 done · 1 undone · About 30 min saved (estimate)") fed by a tenant-scoped aggregation over the decision ledger, with simulation rows kept apart and time saved computed from a fixed, read-only minutes-per-kind table.**

## What was built

- **Package** `backend/autonomous_ops/reporting/`: `__init__.py` holds every Phase 86 constant named in the plan contract (windows, state groups, `MINUTES_PER_KIND` as a `MappingProxyType`, export cap, digest and go-live constants). `stats.py` has `compute`, `fold`, `time_saved`, `format_minutes`, `statistics_payload` (120 lines). `rule_names.py` maps the 14 rule ids the product writes to plain names, falling back to `Automatic decision ({origin})` for `gate:*` ids and the id itself otherwise.
- **Route** `GET /api/autonomous-ops/statistics` in `autonomous_ops_reporting_endpoints.py`, mounted under `AUTONOMOUS_OPS_GUARD`: `days` must be 7, 30 or 90 (else 422), a tenant role may only name its own tenant (403), platform staff must name one (400), the platform organization answers 409.
- **UI** `StatsCard` (139 lines) with the three summary shapes, loading skeleton, load-failed summary, expand toggle, period pills and the four headline cells (Decisions, Done, Undone, Time saved with an Estimate chip). Mounted in `AutonomousOpsActivity` between the Service desk card and Activity, tenant scope only; the screen owns `statsDays`.
- **Copy gate**: the reporting endpoints module, the reporting service, the `reporting` package and `components/autonomousOpsStats` are scanned by ACTV-08 on the pytest and vitest sides.

## Task Commits

| Task | Phase | Commit | Message |
|------|-------|--------|---------|
| 1 (tracer) | RED | fd337f721 | test(86-01): add failing tests for the statistics tracer |
| 1 (tracer) | GREEN | 09dc9a97a | feat(86-01): Statistics card fed by GET /api/autonomous-ops/statistics |
| 2 | RED | 74d5041b7 | test(86-01): add failing tests for the statistics columns and rule names |
| 2 | GREEN | 5bf21c7ea | feat(86-01): complete the statistics column map and plain rule names |
| 3 | n/a | fb6e8dd7f | test(86-01): register the reporting files and folders in the ACTV-08 copy gate |

## TDD Gate Compliance

The plan is `type: execute`; Task 1 (tracer) and Task 2 (`tdd="true"`) were run test-first after a mid-run coordinator correction. I had written only the constants module (`__init__.py`) before the correction arrived, so no implementation preceded a failing test. Task 3 is not marked tdd.

- **RED, Task 1:** target `test_minutes_format_in_plain_words` failed on `assert '' == '0 min'` against an inert `stats.py` skeleton (so imports resolve and failures are assertions, not load errors). Evidence from the pytest JUnit report passed `gsd-tools check tdd-red-evidence` with `RED_EVIDENCE_OK`. Semantic assessment: the target ran and failed on the planned formatting assertion; the HTTP tests errored at fixture setup (router module absent), which is why they were not used as the target. The vitest side failed 6/6 on empty-string assertions.
- **RED, Task 2:** target `test_expired_cancelled_and_refused_rows_count_refused_and_failed_counts_failed` failed on `(0, 0, 4) != (3, 1, 4)`, `RED_EVIDENCE_OK`. Seven tests failed (approved, denied, refused/failed columns, rule names); the window, ordering, isolation, completeness and role tests already passed because the tracer implemented them. That is the intended split: the tracer is the thin path, Task 2 pins the semantics.
- **GREEN:** both feat commits pass their tests. No refactor commit was needed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Copy-gate file count in the vitest side**
- **Found during:** Task 3
- **Issue:** `autonomousOpsCopy.test.ts` pins `FRONTEND_FILES` to length 21; registering `services/autonomousOpsReporting.ts` makes it 22.
- **Fix:** updated the pinned count to 22.
- **Files modified:** src/__tests__/autonomousOpsCopy.test.ts
- **Commit:** fb6e8dd7f

**2. [Rule 3 - Blocking] Test-harness correction for the load-failure test**
- **Found during:** Task 1 GREEN
- **Issue:** `beforeEach(() => fetchStats.mockReset())` returned the mock, which vitest runs as a teardown, producing a stray rejection.
- **Fix:** braces around the hook body, and `mockImplementation(() => Promise.reject(...))` for the failing case.
- **Commit:** 09dc9a97a

**3. [Plan note] Period pills added in Task 1**
- The plan listed only the four headline cells for Task 1's expanded body; the 7/30/90 pills and the "Updated" clock were added because the required `days` and `onDaysChange` props would otherwise be unused. The by-rule table, simulation line, time-saved method block and empty state are left to the later UI plan.

**4. [Plan note] Test harness lives in the test file**
- `tests/_autonomous_ops_http.Api` does not mount the reporting router, so `test_autonomous_ops_stats.py` carries its own small `StatsApi` (same pattern) instead of editing the shared harness.

None of these changed behaviour specified by the plan.

## Verification

- `pytest` stats, catalogue slice, route auth baseline, structural, copy gate and endpoints on the private mongod (27998): 123 passed, 0 skipped.
- `npx vitest run src/__tests__`: 127 files, 2069 tests passed.
- Acceptance greps: 5 functions in stats.py, StatsCard referenced twice in the Activity screen, 0 `dangerouslySetInnerHTML`, all new files under 500 lines.
- Nothing was run against the live database (27017), no restart, no UI publish, no push.

## Known Stubs

None. The Statistics card body is intentionally partial (see deviation 3); the remaining sections are assigned to the later UI plan, not stubbed.

## Threat Flags

None. The one new endpoint is the plan's T-86-01/T-86-02 surface; tenant resolution, window validation and explicit `tenantId` in every `$match` are covered by tests.

## Notes for later plans

- `StatsCard` currently ignores `shadowOnly`, `canExport` and `rules` in the UI; the payload carries them for 86-02+ (by-rule table, simulation line, Export button).
- The plan text "one microsecond earlier" is exercised as written; BSON truncation to milliseconds makes it one millisecond earlier in storage.

## Self-Check: PASSED

All nine created files exist and all five commits (fd337f721, 09dc9a97a, 74d5041b7, 5bf21c7ea, fb6e8dd7f) are ancestors of HEAD.
