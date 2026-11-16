---
phase: 78-organization-endpoint-cost-api
plan: 09
subsystem: testing
tags: [itam, cost, depreciation, golden-table, tenant-isolation, mongodb, pytest]

requires:
  - phase: 78-organization-endpoint-cost-api
    provides: itam_cost_service (78-01, extended by 78-03), the module this plan pins
provides:
  - backend/tests/test_itam_cost_service.py: golden table, reason invariant, lifecycle rule, malformed-input guards, tenant refusal, platform-admin ambient proof, D-08 order, one clock read, static source scan
  - a hardened compute_asset_cost / sort_cost_rows that survive non-string lifecycleStatus, name, tag and id
affects: [78-10, phase-80]

actuals:
  tokens: 28000
  tasks: 2
  commits: 4
plan_head_before: 5dff485d010390914dc3fd833cc474a84f1f97c7
plan_head_after: 3e8cb68dba430a5a7662a07553b137b8e8d6fe83

tech-stack:
  added: []
  patterns:
    - "Golden table asserted on compute_book_value and on compute_asset_cost at the same now"
    - "Loader refusal tested against a database stand-in that fails the test if touched"
    - "Cost modules scanned as source text for forbidden constructs"

key-files:
  created:
    - backend/tests/test_itam_cost_service.py
  modified:
    - backend/itam_cost_service.py

key-decisions:
  - "A non-string or empty lifecycleStatus reads as the default status (deployable) instead of raising"
  - "sort_cost_rows compares name, assetTag and assetId as strings so a stored number cannot break the order"
  - "The salvage-above-cost golden row (150000 at a cost of 100000) is pinned as the platform definition, not corrected"

requirements-completed: [COST-01, COST-02, COST-06, COST-07]

coverage:
  - id: D1
    description: "compute_asset_cost reproduces compute_book_value on all 13 golden rows at the same now; itam_finance_service.py is unchanged"
    requirement: COST-01
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_cost_service.py#test_golden_table"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every unvalued asset carries exactly one reason; valued plus reason counts equals total with includeDisposed false and true; totals with no data are {cents: null, hasData: false}; $0 price is priced; future date keeps the full price and is flagged"
    requirement: COST-02
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_cost_service.py#test_reason_precedence_and_invariant"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_cost_service.py#test_summary_has_data_convention"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_cost_service.py#test_zero_price_is_priced"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_cost_service.py#test_future_date_flag"
        status: pass
    human_judgment: false
  - id: D3
    description: "Disposed and retired rows carry reason equal to status, null book value and their purchase cost; other statuses are valued; the default list hides them and counts excludedByLifecycle"
    requirement: COST-06
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_cost_service.py#test_lifecycle_rule"
        status: pass
    human_judgment: false
  - id: D4
    description: "Malformed cost, policy, date, lifecycleStatus, name, tag and id never raise and never yield a float"
    requirement: COST-02
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_cost_service.py#test_malformed_inputs_never_raise"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_cost_service.py#test_malformed_documents_do_not_fail_the_tenant_read"
        status: pass
    human_judgment: false
  - id: D5
    description: "All four entry points refuse empty, None and platform-admin before reading; the explicit tenantId filter returns only the named tenant under a platform-admin ambient; the cost modules carry no join, cache, finance filter, x100, float conversion or raw handle"
    requirement: COST-07
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_cost_service.py#test_require_tenant_refuses_platform_admin_and_empty"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_cost_service.py#test_explicit_tenant_filter_under_platform_admin_ambient"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_cost_service.py#test_cost_modules_have_no_forbidden_constructs"
        status: pass
    human_judgment: false
  - id: D6
    description: "D-08 order and one clock read per computation"
    requirement: COST-01
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_cost_service.py#test_sort_order"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_cost_service.py#test_one_utc_now_per_computation"
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-11-16
status: complete
---

# Phase 78 Plan 09: Shared cost computation test pin Summary

**The shared per-asset cost computation is pinned by a 13-row golden table on both `compute_book_value` and `compute_asset_cost`, plus reason, lifecycle, malformed-input, tenant-refusal and static-scan guards; the pinning found and fixed one real crash on malformed documents**

## Result

- Plan verification command (`test_itam_cost_service.py`, `test_itam_cost_endpoints.py`, `test_itam_cost_assets.py`, `test_itam_finance_bookvalue.py`): **130 passed, 0 failed, 0 skipped**.
- `-k golden`: 13 passed. The platform-admin ambient test ran against real MongoDB (precondition ping succeeded) and was not skipped.
- Consumers re-run after the fix (`test_itam_cost_isolation.py`, `test_itam_kpi_cost_rules.py`, `test_itam_report_cost_rules.py`): 56 passed.
- `backend/itam_finance_service.py`: untouched by this plan and empty in `git diff 5dff485d0 HEAD`.
- `backend/tests/test_itam_cost_service.py` is 436 lines; `backend/itam_cost_service.py` is 338 lines (both under 500).

## Accomplishments

- Golden table of 13 rows (leap day, anniversary, salvage above and equal to cost, cost 0, future date, integer division, past end of life, Z suffix) asserted for `compute_book_value` directly and for `compute_asset_cost` with a matching asset and model document; the salvage-above-cost row is pinned as the platform definition.
- Reason invariant `valued + sum(reasons) == total` over nine mixed assets with `includeDisposed` false and true, one reason per unvalued row, in the documented precedence.
- Lifecycle rule (disposed/retired reason equals status; archived, broken, deployable, deployed and status-less valued; default list hides and counts them), $0 price, future-date flag, asset-level policy fields ignored, seven unusable-policy shapes, null-not-zero totals for empty, unpriced and priced-but-unvalued tenants.
- Tenant refusal for `compute_tenant_costs`, `load_tenant_assets`, `load_models_by_id` and `load_agents_by_asset` (12 cases) against a database stand-in that fails if touched; real-Mongo proof that the explicit `tenantId` filter holds under a `platform-admin` ambient (the premise that the wrapper adds no filter there is asserted first, a foreign tenant's agent and same-id model are not joined or used).
- D-08 order with all four tiebreaks, exactly one `utc_now()` per computation (and one for the detail computation), static scan of the three cost modules.

## RED / GREEN notes

Task 1 pinned code that already existed, so its tests were green on first run (the plan's own framing: "test-first against existing code"); there was no RED for it. Task 2 had a real RED: 7 cases failed against the module as 78-03 left it (see deviation). RED commit `262346e1e` precedes the fix `7660a8cf0`.

## Task Commits

1. Task 1 (tracer): `64813dabd` test(78-09) golden table, reason invariant, lifecycle rule
2. Task 2 RED: `262346e1e` test(78-09) guards (7 cases failing, cited in the message)
3. Task 2 fix: `7660a8cf0` fix(78-09) malformed lifecycleStatus and non-string name/tag/id
4. Task 2 naming: `3e8cb68db` test(78-09) test names as the plan lists them (adds `test_malformed_inputs_never_raise`, renames the sort test)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] A malformed lifecycleStatus or non-string name, tag or id broke the cost computation**
- **Found during:** Task 2 (malformed-input tests)
- **Issue:** `compute_asset_cost` did `status_value in INACTIVE_STATUSES`, which raises `TypeError: unhashable type` for a list or dict `lifecycleStatus`, failing the whole tenant read (threat T-78-23); an int, float or bool status was echoed as the row status. `sort_cost_rows` raised `TypeError` comparing an int name, tag or id with a string on tied book values. The function's own docstring promises it never raises for any document shape.
- **Fix:** a non-string or empty `lifecycleStatus` reads as the default status; the sort key compares name, assetTag and assetId as strings. `compute_book_value` and the assertions were not touched.
- **Files modified:** `backend/itam_cost_service.py` (+6/-4)
- **Verification:** 7 previously failing cases pass; 78-01/78-03 suites (endpoints, assets) plus isolation, KPI and report cost-rule suites all pass.
- **Commit:** `7660a8cf0`

**Total deviations:** 1 auto-fixed (Rule 1). **Impact:** hardening only; no figure for a well-formed document changes. Asset ids that are themselves unhashable (list or dict `id`) would still fail `compute_tenant_costs`; asset ids are generated strings, so this was left out of scope and is not asserted.

## Authentication Gates

None.

## Known Stubs

None.

## Threat Flags

None. T-78-22 (golden table, finance file unchanged), T-78-23 (malformed inputs) and T-78-24 (loader refusal, platform-admin ambient test, static scan) are mitigated as planned.

## Issues Encountered

None. Working-tree commits used `-c core.fileMode=false` and explicit paths; the user's roughly 2,300 uncommitted files were not staged. No test process was left running.

## Next Phase Readiness

Ready for 78-10 (and 78-08 if still open). The static scan will fail any later edit that adds a join, cache, finance filter, x100 or float conversion to the three cost modules.

## Self-Check: PASSED

Created `backend/tests/test_itam_cost_service.py` found; commits `64813dabd`, `262346e1e`, `7660a8cf0`, `3e8cb68db` present on branch npx.
