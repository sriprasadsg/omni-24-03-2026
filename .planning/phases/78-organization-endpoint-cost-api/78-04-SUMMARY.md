---
phase: 78-organization-endpoint-cost-api
plan: 04
subsystem: api
tags: [itam, kpi, cost, depreciation, tenant-isolation, fastapi, mongodb]

requires:
  - phase: 78-organization-endpoint-cost-api
    provides: itam_cost_service.compute_asset_cost / load_models_by_id / utc_now, resolve_itam_tenant (78-01)
provides:
  - "/api/itam/kpis asset value on the shared per-asset computation (tile equals the cost summary)"
  - "assetValue.inScopeAssetCount and assetValue.valuedCount (consumed by the 78-02 tile)"
  - "/api/itam/kpis on the shared tenant resolver (400 for platform-admin, Owner header honoured)"
affects: [78-05, 78-07, 78-08, phase-80]

actuals:
  tokens: 6500
  tasks: 2
  commits: 3
plan_head_before: 1ea81c3060a99e81a87116118c0c2da32025c0ca
plan_head_after: fd8ddbb42848e616a2383d5d7f5e5cdd25d32efb

tech-stack:
  added: []
  patterns:
    - "One clock read per compute_itam_kpis call, passed to every KPI"
    - "Money KPI excludes disposed/retired; inventory pie and assetCount keep every status"

key-files:
  created:
    - backend/tests/test_itam_kpi_cost_rules.py
  modified:
    - backend/itam_reporting_kpis.py
    - backend/itam_kpi_endpoints.py
    - backend/tests/test_itam_reporting_kpis.py

key-decisions:
  - "assetValue.assetCount keeps meaning every asset (the pie total, A-78-13); the tile's Valued X of Y uses inScopeAssetCount and valuedCount"
  - "No valued asset gives totalBookValueCents null with hasData true, so the tile can show Not tracked (D-10)"

requirements-completed: [COST-01, COST-06, COST-07]

coverage:
  - id: D1
    description: "KPI totalBookValueCents and valuedCount equal the cost summary's bookValueTotal and coverage.valued for the same tenant and clock"
    requirement: COST-01
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_kpi_cost_rules.py#TestAssetValueRules::test_kpi_equals_shared_computation"
        status: pass
    human_judgment: false
  - id: D2
    description: "Disposed and retired assets add nothing to the tile's money and inScopeAssetCount, while assetCount and the status pie still count every status"
    requirement: COST-06
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_kpi_cost_rules.py#TestAssetValueRules::test_disposed_and_retired_leave_value_but_stay_in_pie"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_kpi_cost_rules.py#TestAssetValueRules::test_all_assets_inactive"
        status: pass
    human_judgment: false
  - id: D3
    description: "Assets with none valued give a null total with hasData true; a tenant with no assets keeps hasData false with null numbers; withoutPolicyCount equals inScope minus valued"
    requirement: COST-01
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_kpi_cost_rules.py#TestAssetValueRules::test_null_book_value_with_assets_keeps_has_data"
        status: pass
      - kind: unit
        ref: "backend/tests/test_itam_kpi_cost_rules.py#TestAssetValueRules::test_no_assets_payload"
        status: pass
    human_judgment: false
  - id: D4
    description: "GET /api/itam/kpis covers one resolved tenant: an Owner's X-Tenant-ID scopes asset, licence, warranty and overdue reads; Owner without a choice, Support and platform-admin get 400 Select a tenant"
    requirement: COST-07
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_kpi_cost_rules.py#TestTenantScoping::test_owner_header_scopes_every_kpi"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_kpi_cost_rules.py#TestTenantScoping::test_kpi_owner_without_tenant_is_400"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_reporting_kpis.py#TestItamKpiRoute::test_get_kpis_returns_400_when_no_tenant_id"
        status: pass
    human_judgment: false
  - id: D5
    description: "One compute_itam_kpis call reads utc_now exactly once; the compute_itam_kpis(db, tenant_id) signature is unchanged"
    requirement: COST-01
    verification:
      - kind: unit
        ref: "backend/tests/test_itam_kpi_cost_rules.py#TestAssetValueRules::test_one_utc_now_per_kpi_request"
        status: pass
    human_judgment: false

duration: 10min
completed: 2026-11-16
status: complete
---

# Phase 78 Plan 04: KPI tile on the shared cost computation Summary

**The ITAM KPI tile's asset value now comes from `compute_asset_cost` (leaving disposed and retired assets out of the money while the pie keeps them), returns null instead of 0, exposes `inScopeAssetCount` and `valuedCount`, and `/api/itam/kpis` covers exactly one resolved tenant through `resolve_itam_tenant`.**

## Accomplishments

- `_compute_asset_value_kpi(db, tenant_id, assets, now)` uses one `load_models_by_id` read and one `compute_asset_cost` per asset; no own model query, loop logic or clock. For the same tenant and `utc_now` the tile equals the cost summary's `bookValueTotal.cents`, `coverage.valued` and `coverage.total` (asserted).
- `compute_itam_kpis(db, tenant_id)` keeps its signature, reads `itam_cost_service.utc_now()` once, passes that `now` to every KPI, and its assets read carries an explicit `tenantId` filter.
- `GET /api/itam/kpis` calls `resolve_itam_tenant(request, current_user)` as the first statement before `get_database()`. A tenant user reads their own tenant, an Owner session reads the X-Tenant-ID tenant, and platform-admin, Support and an empty context get 400 "Select a tenant". The real-Mongo Owner-with-header test shows seat totals (42, not 49), asset value and overdue counts come only from the header tenant; a mutation run with the resolver's `set_tenant_id` disabled makes that test fail, so the ambient re-alignment is what scopes the licence, warranty and overdue reads (T-78-12).

## Visible tile change (D-04)

A tenant with disposed or retired assets will see its Total Asset Value tile drop on the next backend restart: those assets no longer contribute book value and are not in `inScopeAssetCount`. The lifecycle pie and `assetCount` are unchanged (every status still counted). A tenant whose assets are all unvalued now reads "Not tracked" (null total, `hasData` true) instead of $0. A Super Admin with no chosen tenant now gets 400 on this route instead of a blended total (T-78-11).

## Task Commits

1. Task 1 RED: `b27c84a44` test(78-04) null-not-0 and 400 assertions (2 failed: `0 is None`, `403 == 400`)
2. Task 1 GREEN: `726686d9d` feat(78-04) KPI on shared computation, route on the resolver
3. Task 2: `fd8ddbb42` test(78-04) KPI cost rules (11 tests)

## TDD Gate Compliance

Task 1 RED failed on the two target assertions named in the plan (`totalBookValueCents is None` got 0; status 400 got 403), not on load or fixture errors; `workflow.tdd_mode` is false so the format classifier was not run. GREEN then passed all 29 tests. Tracer gate: the Task 1 verify command was re-run after the commit (29 passed) before Task 2 started. Task 2 is tests over code already landed in Task 1, so its tests passed on first run (no separate RED); the scoping test was mutation-checked as described above.

## Deviations from Plan

None - plan executed exactly as written. (The `Task 2` note "if a case fails fix itam_reporting_kpis.py" did not trigger: every case passed first run.)

## Verification

- `backend/venv/bin/python -m pytest backend/tests/test_itam_kpi_cost_rules.py backend/tests/test_itam_reporting_kpis.py backend/tests/test_itam_cost_endpoints.py backend/tests/test_catalogue_slice_assets.py -q -p no:cacheprovider -rs`: 48 passed, 0 failed, 0 skipped (mongod up).
- Acceptance greps: `resolve_itam_tenant(request, current_user)` 1 (line 43, before `get_database()` at line 45); `itam_cost_service.utc_now()` 1; `datetime.now(` 0; `compute_asset_cost(` 1; `inScopeAssetCount` 4; renamed test present once. Line counts: reporting_kpis 296, its test 468, new test module 304 (all under 500).

## Authentication Gates

None.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register: T-78-11 (platform-admin/empty context 400 before any read) and T-78-12 (resolver's ambient tenant write, proven on real Mongo) are mitigated as specified.

## Issues Encountered

None. The working tree's roughly 2,300 uncommitted user files were left alone; only the four plan files were staged by explicit path.

## Next Phase Readiness

Ready for 78-05 (Asset value report on the same computation). The KPI fields `inScopeAssetCount` and `valuedCount` that 78-02's tile consumes are now served. The backend runs from the checkout, so the tile figures change when the user next restarts it.

## Self-Check: PASSED

Files found: backend/tests/test_itam_kpi_cost_rules.py, backend/itam_reporting_kpis.py, backend/itam_kpi_endpoints.py. Commits b27c84a44, 726686d9d, fd8ddbb42 present on branch npx.
