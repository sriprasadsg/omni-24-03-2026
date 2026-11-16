---
phase: 78-organization-endpoint-cost-api
plan: 05
subsystem: api
tags: [itam, reports, cost, depreciation, tenant-isolation, fastapi]

requires:
  - phase: 78-organization-endpoint-cost-api
    provides: itam_cost_service.compute_asset_cost / sort_cost_rows / load_tenant_assets / load_models_by_id / utc_now, resolve_itam_tenant (78-01)
provides:
  - "Asset value pre-built report rows from the shared per-asset cost computation (disposed and retired dropped, D-08 order)"
  - "POST /api/itam/reports/prebuilt/{key}/run and /export on the shared tenant resolver for every report key"
  - "Custom report builder Book Value column from compute_asset_cost"
affects: [78-06, 78-09, phase-80]

actuals:
  tokens: 6600
  tasks: 2
  commits: 3
plan_head_before: 66f0a97a98660b6426a0db3363d2ff3154c212d3
plan_head_after: 964728360a4ca115e7e76c86ff73aba53713988b

tech-stack:
  added: []
  patterns:
    - "Report builders take figures from the one shared computation and format only"
    - "Resolver is the first statement of the handler body, ahead of every other check"

key-files:
  created:
    - backend/tests/test_itam_report_cost_rules.py
  modified:
    - backend/itam_reporting_prebuilt.py
    - backend/itam_reporting_endpoints.py
    - backend/itam_reporting_filters.py

key-decisions:
  - "Resolver runs before the export format check, so an unsupported format from a platform session is 400 Select a tenant, not the format message"
  - "Report population stays stored cost and date both present (A-78-14); not-tracked assets without a purchase record appear in the cost list but not the report"
  - "A non-integer stored cost (for example a float) now reads as unreadable_purchase_cost in the custom report too, because the shared rule is integer cents only"

requirements-completed: [COST-01, COST-06, COST-07]

coverage:
  - id: D1
    description: "Asset value report rows equal compute_asset_cost for each asset at one clock read, in sort_cost_rows order, with one model read"
    requirement: COST-01
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_report_cost_rules.py#TestAssetValueReportRules::test_asset_value_rows_match_shared_computation"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_report_cost_rules.py#TestAssetValueReportRules::test_asset_value_sort_tiebreak"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_report_cost_rules.py#TestAssetValueReportRules::test_report_takes_one_clock_read_and_one_model_read"
        status: pass
    human_judgment: false
  - id: D2
    description: "Disposed and retired assets leave the Asset value report; archived, broken, deployable, deployed and status-less assets stay"
    requirement: COST-06
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_report_cost_rules.py#TestAssetValueReportRules::test_asset_value_report_drops_disposed_and_retired"
        status: pass
    human_judgment: false
  - id: D3
    description: "A malformed cost or date degrades to a dash and a reason code; the run still returns 200"
    requirement: COST-01
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_report_cost_rules.py#TestAssetValueReportRules::test_malformed_inputs_do_not_fail_the_report"
        status: pass
    human_judgment: false
  - id: D4
    description: "Pre-built run and export cover one resolved tenant for every report key: Owner header scopes the report and the export record, platform context and no choice give 400 before any database work, Support gets 403"
    requirement: COST-07
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_report_cost_rules.py#TestPrebuiltTenantResolution"
        status: pass
    human_judgment: false
  - id: D5
    description: "The custom builder's Book Value column matches the shared computation and shows a dash for disposed, retired and no-policy assets while the rows stay listed"
    requirement: COST-06
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_report_cost_rules.py#TestCustomReportBookValue"
        status: pass
    human_judgment: false

duration: ~10min
completed: 2026-11-16
status: complete
---

# Phase 78 Plan 05: Asset value report and custom Book Value on the shared cost computation Summary

**The Asset value report and the custom report builder's Book Value column now compute through `compute_asset_cost` (disposed and retired assets leave the report, rows in the shared D-08 order), and the pre-built run and export routes cover exactly one tenant through `resolve_itam_tenant`.**

## Accomplishments

- `_build_asset_value_rows` is one tenant-scoped assets read, one `load_models_by_id` read, one `itam_cost_service.utc_now()`, then `compute_asset_cost` and `sort_cost_rows`; it only formats. Each row's Book Value therefore equals that asset's `bookValueCents` in the cost list. Population is unchanged (stored cost and date both present) minus disposed and retired (D-04).
- `run_prebuilt_report` and `export_prebuilt_report` call `resolve_itam_tenant(request, current_user)` as their first statement, before the format check, `_ensure_reports_dir()` and `get_database()`. An Owner session with `X-Tenant-ID` runs and exports that tenant's report (the spy shows `build_report_rows` and `generate` receive the header tenant and the ambient tenant matches); an Owner with no choice gets 400 "Select a tenant" with the database never reached, for every report key.
- `_compute_finance_result` takes `bookValueCents` from `compute_asset_cost` (the fourth copy of the loop is gone); `run_custom_report` reads `itam_cost_service.utc_now()` so one patched clock drives book value and warranty. Row selection, filters, joins and sorting are untouched.

## Line counts

| File | Before | After |
|------|--------|-------|
| backend/itam_reporting_prebuilt.py | 476 | 432 |
| backend/itam_reporting_filters.py | 499 | 482 |
| backend/itam_reporting_endpoints.py | 352 | 358 |
| backend/tests/test_itam_report_cost_rules.py (new) | 0 | 316 |

## Task Commits

1. Task 1 RED: `5eabba81e` test(78-05) failing report rules and resolution tests (10 failed on the target assertions: extra disposed/retired rows, 200 instead of 400, wrong tenant)
2. Task 1 GREEN: `2da5a1b36` feat(78-05) report on the shared computation, routes on the resolver
3. Task 2: `964728360` feat(78-05) custom report Book Value on the shared computation (tests and code in one commit)

## TDD Gate Compliance

Task 1 RED `5eabba81e` precedes GREEN `2da5a1b36`; RED failed on the planned assertions, not on load errors. Three of the 13 tests (shared-computation match, Support 403, tenant admin header ignored) already passed at RED because they pin behaviour the old code also had. Tracer gate: the Task 1 verify command was green at commit and re-run before Task 2 (72 passed). Task 2 was committed as a single feat commit with its tests (no separate RED), because the existing builder suite already pinned the old behaviour and the new tests only add the dash cases.

## Deviations from Plan

None - plan executed exactly as written. No existing assertion in `test_itam_reporting_prebuilt.py` or any other existing test needed changing; all passed unchanged.

## Visible behaviour changes (D-04, D-13)

- A tenant's Asset value report loses its disposed and retired rows on the next backend restart; its remaining Book Values follow the shared rules.
- A Super Admin who runs or exports any pre-built report without choosing a tenant now gets 400 instead of a blended report; the Reports page buttons are disabled with a note in 78-06.
- A custom report shows a dash (not a depreciated figure) in Book Value for disposed, retired, and no-policy assets, and an asset whose stored cost is not an integer (for example a float) now shows a dash there too, because the shared computation accepts integer cents only.

## Authentication Gates

None.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register: T-78-13 mitigated (resolver first, 400 tests prove no database read, export spy proves the resolved tenant is recorded); T-78-14 unchanged (download tenant check).

## Issues Encountered

None. The roughly 2,300 uncommitted user files were left alone; only the four plan files were staged by explicit path. The custom report routes and the download route are unchanged (A-78-17), so a Super Admin's saved custom reports behave as before.

## Verification

- `backend/venv/bin/python -m pytest backend/tests/test_itam_report_cost_rules.py backend/tests/test_itam_reporting_prebuilt.py backend/tests/test_itam_reporting_builder.py backend/tests/test_itam_reporting_export.py backend/tests/test_itam_api_integrations.py -q -p no:cacheprovider -rs`: 129 passed, 0 failed, 0 skipped.
- Acceptance greps: `compute_asset_cost(` 1 and `sort_cost_rows(` 1 in the prebuilt module; `resolve_itam_tenant(request, current_user)` 2 in the endpoints module; `compute_asset_cost(` 1 and `itam_cost_service.utc_now()` 1 in the filters module; line caps 432 (at most 476) and 482 (at most 499).

## Next Phase Readiness

Ready for 78-06 (Reports page note when no tenant is chosen). The backend runs from the checkout, so these changes take effect on the user's next restart.

## Self-Check: PASSED

Files found: backend/tests/test_itam_report_cost_rules.py, backend/itam_reporting_prebuilt.py, backend/itam_reporting_endpoints.py, backend/itam_reporting_filters.py. Commits 5eabba81e, 2da5a1b36, 964728360 present on branch npx.
