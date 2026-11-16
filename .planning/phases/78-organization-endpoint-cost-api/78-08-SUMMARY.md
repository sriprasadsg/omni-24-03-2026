---
phase: 78-organization-endpoint-cost-api
plan: 08
subsystem: testing
tags: [itam, cost, parity, scale, tenant-isolation, mongodb, pytest]

requires:
  - phase: 78-organization-endpoint-cost-api
    provides: itam_cost_service (78-01, 78-03, 78-09), KPI on it (78-04), Asset value report on it (78-05), isolation proof (78-07)
provides:
  - backend/tests/test_itam_cost_parity.py: four-way parity (KPI tile, Asset value report, cost summary, cost list) plus the per-asset book-value route over one seeded tenant
  - backend/tests/test_itam_cost_scale.py: 20,000-asset read-count and timing bound
affects: [78-10, phase-80]

actuals:
  tokens: 5100
  tasks: 2
  commits: 2
plan_head_before: 19dfb6a6173a41d12f59c05cfa0bda8a171dd5bd
plan_head_after: 1e576396081c4dbb53e3797b45fd067d64527bc3

tech-stack:
  added: []
  patterns:
    - "Expected book values derived through compute_book_value at the fixed clock, never from the implementation's output"
    - "Report money cells parsed with Decimal into integer cents, never float"
    - "Counting proxy over TenantIsolatedDatabase counts find per collection for the real routes"

key-files:
  created:
    - backend/tests/test_itam_cost_parity.py
    - backend/tests/test_itam_cost_scale.py
  modified: []

key-decisions:
  - "No production code changed: parity held on the first run and the agents $in over 19,500 ids is fast, so the bounded agents fallback (A3) was not needed"
  - "The scale test asserts the KPI's cost read (asset_models once) but not a single assets read: the overdue KPI reads assets twice more for its own rows"

requirements-completed: [COST-01, COST-02, COST-03, COST-06, COST-07]

coverage:
  - id: D1
    description: "KPI totalBookValueCents, cost summary bookValueTotal, the Asset value report's Book Value sum (Decimal) and the sum of list-row bookValueCents are the same integer for one seeded tenant under one fixed clock; KPI valuedCount and inScopeAssetCount equal coverage.valued and coverage.total"
    requirement: COST-01
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_cost_parity.py#TestParity::test_kpi_report_summary_and_list_agree"
        status: pass
    human_judgment: false
  - id: D2
    description: "The report and the list agree row for row (value, reason, order), and the per-asset book-value route returns the list row's bookValueCents for every active asset with well-typed inputs"
    requirement: COST-01
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_cost_parity.py#TestParity::test_report_matches_list_row_for_row"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_cost_parity.py#TestParity::test_book_value_route_matches_list"
        status: pass
    human_judgment: false
  - id: D3
    description: "Disposed and retired assets are absent from the KPI value, the report and the default list; includeDisposed raises purchaseTotal by exactly their two costs and leaves bookValueTotal unchanged; the KPI pie still counts them"
    requirement: COST-06
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_cost_parity.py#TestParity::test_lifecycle_rule_across_surfaces"
        status: pass
    human_judgment: false
  - id: D4
    description: "Not-tracked cases (no purchase record, no policy, malformed cost, unparseable date) are null with one reason each and add nothing to either total; the $0 and future-date assets are priced; the agent/manual serial pair is marked on both rows and counts as one pair"
    requirement: COST-03
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_cost_parity.py#TestParity::test_not_tracked_and_flags"
        status: pass
    human_judgment: false
  - id: D5
    description: "Repeat runs under a fixed clock return identical KPI, report, summary and list figures; a second tenant with overlapping tags, model ids and a same-serial pair never reaches tenant-p's figures"
    requirement: COST-01
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_cost_parity.py#TestParity::test_repeat_runs_identical"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_cost_parity.py#TestParity::test_other_tenant_never_leaks"
        status: pass
    human_judgment: false
  - id: D6
    description: "A 20,000-asset tenant is served with one assets read, at most one asset_models read and no agents read for the summary; one read each of assets, asset_models and agents for the list; one asset_models read for the KPI; the list finishes well inside 10 seconds; the other tenant's assets never appear"
    requirement: COST-07
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_cost_scale.py#test_large_tenant_reads_are_bounded"
        status: pass
    human_judgment: false

duration: 14min
completed: 2026-11-16
status: complete
---

# Phase 78 Plan 08: Cost parity and scale Summary

**Four-way real-Mongo parity (KPI tile, Asset value report, cost summary, cost list) plus the per-asset book-value route over one seeded tenant, and a 20,000-asset read-count and timing bound, with no production code change**

## Performance

- **Duration:** 14 min
- **Tasks:** 2 (tracer + scale)
- **Files:** 2 created, 0 modified

## Accomplishments

- One seeded tenant (tenant-p, 14 assets) covers every D-01..D-12 case: deployed, deployable, archived, broken and status-less valued assets, one disposed and one retired asset with valid policies, a priced asset whose model is gone, an agent computer with `serial:XYZ789` and a linked agent, a hand-entered `xyz789` asset, a malformed cost ("1000"), an unparseable date ("31/12/2020"), a future date (+400 days) and a $0 cost. Purchase dates are real today minus 50, 200, 500, 900 and 1300 days. A second tenant (tenant-q) holds the same tags and names, a same-id model with a different policy, an agent and a same-serial pair as noise.
- Under one patched `itam_cost_service.utc_now` the four surfaces return the same integer total (KPI `totalBookValueCents`, summary `bookValueTotal.cents`, Decimal-parsed report column sum, list-row sum), all equal to the sum derived independently through `compute_book_value`. KPI `valuedCount` and `inScopeAssetCount` equal `coverage.valued` and `coverage.total`.
- The report equals the list row for row (value, reason, order); `get_asset_book_value` equals the list row for every active asset except the string-cost one (12 checked).
- No parity mismatch: nothing in `itam_cost_service.py`, the KPI, the report or the finance route needed a fix.

## Scale timings (COST-07, read by 78-10)

20,000 assets for tenant-s (19,500 in scope after 500 disposed, 2,000 agents linked by assetId, one third with a policy, 1,000 assets in tenant-t). Three runs of `test_large_tenant_reads_are_bounded`, in seconds:

| Surface | Run 1 | Run 2 | Run 3 | Bound |
|---------|-------|-------|-------|-------|
| Summary route | 0.28 | 0.24 | 0.29 | none |
| List route, page 1 of 100 | 0.23 | 0.15 | 0.20 | under 10 |
| KPI (compute_itam_kpis) | 0.23 | 0.19 | 0.25 | none |

Read counts asserted: summary assets 1, asset_models at most 1, agents 0; list assets 1, asset_models 1, agents 1 (total 19,500); KPI asset_models 1. Machine load during measurement: load average 2.5 to 3.1; the earlier executor's broad pytest run (PID 2831734) was still running (about 14 minutes elapsed) and competing for CPU. The bounds hold by a factor of about 40, so no re-measure after it exits was needed. The agents `$in` over 19,500 ids is fast, so the bounded fallback (RESEARCH A3) was not applied and `itam_cost_service.py` is unchanged.

## Task Commits

1. Task 1 (tracer): `b5a9370ae` test(78-08) four-way cost parity across KPI, Asset value report, summary, list and book-value route
2. Task 2: `1e5763960` test(78-08) 20,000-asset tenant is served with one read per collection inside the time bound

## TDD Gate Compliance

This is a test-only plan over already-shipped code (78-01..78-05, 78-09), so there is no RED commit and no GREEN `feat` commit: the new tests passed on first run, which is the intended result (they pin behaviour that exists). The plan's own text calls for fixing the owning module on a mismatch, and none occurred. `workflow.tdd_mode` is false; the format classifier was not run. Tracer gate: the Task 1 verify command passed (7 passed, 0 skipped) before Task 2 started.

## Deviations from Plan

**1. [Rule 2 - Missing critical functionality] Added `test_other_tenant_never_leaks`.** Found during Task 1: the plan seeds tenant-q "noise" but lists no assertion that it never reaches tenant-p's figures (T-78-19 integrity of reported figures). The test asserts no `tenant-q` string, no tenant-q agent and no tenant-q purchase cost in any of the four surfaces. Parity file now has 7 tests (the six named plus this one). Commit `b5a9370ae`.

**2. [Observation, no change] The KPI reads `assets` three times, not once.** `compute_itam_kpis`'s docstring says it reads `db.assets` once; in fact the overdue KPI (`itam_reporting_kpis.py` lines 239 and 245) adds two more finds for its audit and check-in rows. The plan asserts only the KPI's asset_models read (once), which holds, so the scale test asserts that and records the reason in a comment. This is pre-existing, outside the cost computation, and costs 0.2 s at 20,000 assets; left alone. The docstring wording is stale and could be corrected by a later plan.

**Total deviations:** 1 auto-added test (Rule 2), 1 observation. **Impact:** none on behaviour.

## Authentication Gates

None.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register: T-78-19 (four-way parity under one clock), T-78-20 (read-count and time bound at 20,000 assets) and T-78-21 (`mongo_db` drops its database; the omni_test_* list was empty after the four-suite run, apart from a transient database of the other executor's pytest process) are mitigated as specified.

## Issues Encountered

None. The working tree carries the user's uncommitted files; only the two new test files were staged, by explicit path.

## Verification

`backend/venv/bin/python -m pytest backend/tests/test_itam_cost_scale.py backend/tests/test_itam_cost_parity.py backend/tests/test_itam_cost_assets.py backend/tests/test_itam_cost_service.py -q -p no:cacheprovider -rs`: 105 passed, 0 failed, 0 skipped. Line counts: parity 268, scale 147 (both under 500). `grep -c Decimal` on the parity file: 3. The phase command and the full backend suite are 78-10's job and were not run. No deploy, restart, UI publish or push.

## Next Phase Readiness

Ready for 78-10 (phase gate): it reads the timings above.

## Self-Check: PASSED

Files found: backend/tests/test_itam_cost_parity.py, backend/tests/test_itam_cost_scale.py. Commits b5a9370ae and 1e5763960 present on branch npx.
