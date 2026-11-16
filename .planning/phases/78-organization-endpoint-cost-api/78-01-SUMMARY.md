---
phase: 78-organization-endpoint-cost-api
plan: 01
subsystem: api
tags: [itam, cost, depreciation, tenant-isolation, fastapi, mongodb, api-key-scopes]

requires:
  - phase: 59-itam-finance
    provides: compute_book_value (Phase 59 D-04 straight-line depreciation), called unchanged
  - phase: 76-catalogue-guards
    provides: ITAM_API_KEY_GUARD catalogue mount and the assets-slice parity test
provides:
  - itam_cost_service: the one per-asset cost computation (compute_asset_cost) plus tenant loaders, D-08 sort, summary
  - itam_tenant_scope.resolve_itam_tenant: shared Owner-only tenant chooser for cost, KPI and Asset value report routes
  - GET /api/itam/costs/summary (purchaseTotal, bookValueTotal, coverage) on the real app behind ITAM_API_KEY_GUARD
affects: [78-02, 78-03, 78-04, 78-05, 78-09, phase-80]

actuals:
  tokens: 7146
  tasks: 2
  commits: 3
plan_head_before: fd4e00f240eb21dd9fbb08f6c43e7d6877e39e1b
plan_head_after: 85e2f4dc3b0ec3f5cd44d7a547b19be84469863f

tech-stack:
  added: []
  patterns:
    - "Cost figures computed at read time from one shared pure function; nothing persisted"
    - "Tenant resolver is a synchronous call in the handler body (never a dependency) so set_tenant_id reaches the handler context"
    - "Unknown value = None + exactly one reason code, never 0 (D-10)"

key-files:
  created:
    - backend/itam_cost_service.py
    - backend/itam_tenant_scope.py
    - backend/itam_cost_endpoints.py
    - backend/tests/test_itam_cost_endpoints.py
  modified:
    - backend/router_registry.py
    - backend/catalogue_mounts_assets.py
    - backend/tests/test_catalogue_slice_assets.py

key-decisions:
  - "Resolver reads X-Tenant-ID itself because verify_token/verify_token_async reset the ambient tenant after TenantMiddleware (premise grep confirmed, see below)"
  - "Reason precedence: disposed/retired, unreadable_purchase_cost, no_purchase_record, no_depreciation_policy_assigned, unreadable_purchase_date; flags are non-exclusive"
  - "Sessions in the real-app probe use auth session_capable because the route authenticates through get_current_user_or_api_key"

patterns-established:
  - "compute_tenant_costs: two collection reads, one clock read (itam_cost_service.utc_now, the single test patch point)"

requirements-completed: [COST-01, COST-02, COST-06, COST-07]

coverage:
  - id: D1
    description: "GET /api/itam/costs/summary returns one tenant's purchase total, book value total and coverage computed only from that tenant's assets"
    requirement: COST-02
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_cost_endpoints.py#TestSummaryTracer::test_summary_tracer_real_mongo"
        status: pass
    human_judgment: false
  - id: D2
    description: "Disposed and retired assets are out of both totals by default; includeDisposed adds their purchase cost only, book value stays null with reason"
    requirement: COST-06
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_cost_endpoints.py#TestSummaryTracer::test_summary_include_disposed"
        status: pass
    human_judgment: false
  - id: D3
    description: "Book value comes from compute_book_value unchanged; an empty tenant gets hasData false totals, never 0"
    requirement: COST-01
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_cost_endpoints.py#TestSummaryTracer::test_empty_tenant_summary"
        status: pass
    human_judgment: false
  - id: D4
    description: "Tenant resolver: Owner chooses via X-Tenant-ID, Support/tenant users/API keys cannot, empty or platform-admin context is 400 before any database read"
    requirement: COST-07
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_cost_endpoints.py#TestTenantResolver"
        status: pass
    human_judgment: false
  - id: D5
    description: "Route refused (403) for roles without view:itam or manage:assets, Platform Billing and view:assets-scoped keys; admitted for itam_viewer and view:itam / manage:assets keys; parity test sees the router guarded"
    requirement: COST-07
    verification:
      - kind: integration
        ref: "backend/tests/test_catalogue_slice_assets.py#test_itam_cost_routes_enforced_on_real_app"
        status: pass
      - kind: integration
        ref: "backend/tests/test_catalogue_slice_assets.py#test_assets_slice_parity"
        status: pass
    human_judgment: false

duration: 6min
completed: 2026-11-16
status: complete
---

# Phase 78 Plan 01: Cost summary tracer Summary

**One shared per-asset cost computation over the unchanged Phase 59 depreciation, an Owner-only tenant resolver, and GET /api/itam/costs/summary registered on the real app behind the ITAM API-key guard**

## Performance

- **Duration:** 6 min
- **Tasks:** 2 (tracer + registration)
- **Files:** 4 created, 3 modified

## Accomplishments

- `compute_asset_cost` never raises for any document shape; every unvalued asset carries exactly one reason, so `coverage.valued + sum(reasons) == total` (asserted in the tracer).
- Totals with no contributing asset are `{cents: null, hasData: false}` (empty tenant test), never 0 (PROH-78-01).
- `resolve_itam_tenant` gives 400 ("Select a tenant: ...") before `get_database()` for an Owner with no choice, Owner header `platform-admin`, Support, an Owner-role API key and a missing tenant; the ambient tenant is set to the resolved value (spy test).
- Real-app probes: nobody, viewer (view:assets only), Platform Billing and a `view:assets`-scoped key get 403; itam_viewer, itam_admin, `view:itam` and `manage:assets` keys reach the handler (500 in the throwaway-DB probe environment, identical to /api/itam/kpis there).

## Premise grep (D-13, RESEARCH Pitfall 1)

`grep -n "_set_tenant_id(tenant_id)" backend/authentication_service.py` printed exactly two lines, as required:

```
408:        _set_tenant_id(tenant_id)
511:        _set_tenant_id(tenant_id)
```

authentication_service.py was read only, never edited or staged.

## Assumptions as recorded

- A-78-01: priced = valid non-negative integer cost, date or not; cost without date counts in purchaseTotal, book value null, reason no_purchase_record (implemented, flagged).
- A-78-02: six reason codes in the stated precedence plus futurePurchaseDate / possibleDuplicate flags; unreadable_purchase_cost is the planner addition (implemented, flagged; Phase 80 keys on these strings).
- A-78-03: header honoured only for auth_source "session" and platform_tier "owner"; an Owner-role API key resolves to its own tenant, so gets 400 (test_api_key_owner_header_is_ignored).
- A-78-04: 400 detail is "Select a tenant: ITAM figures cover one organization at a time."
- A-78-05: an Owner header naming a tenant with no assets gets 200 empty summary (no existence oracle); `platform-admin` header gets 400. Behaviour follows from the loaders; the unknown-tenant 200 is not separately asserted beyond the empty-tenant test.
- A-78-06: user-accepted 2026-11-16 (D-15 amended), not open: Platform Billing holds no view:itam and is refused 403 by the guard before the resolver; only Support and an Owner with no choice reach the 400. Probed on the real app.

## Task Commits

1. Task 1 RED: `8fe9f982c` test(78-01) failing tests (13)
2. Task 1 GREEN: `7d220bcb8` feat(78-01) cost service, tenant resolver, summary route
3. Task 2: `85e2f4dc3` feat(78-01) router registration, catalogue mount, real-app probes

## TDD Gate Compliance

RED commit `8fe9f982c` precedes GREEN `7d220bcb8`. The RED run failed at collection with `ModuleNotFoundError: No module named 'itam_cost_endpoints'` (the modules did not exist), which the strict RED classifier would call INVALID_RED (a load failure, not a target assertion). `workflow.tdd_mode` is false, so no gate blocked; recorded here for honesty. Task 2's RED was valid: the new probe test returned 404 (unregistered) and the parity assertion failed on `itam_cost_endpoints` missing from the slice before registration. Task 2 was committed as one feat commit (tests plus registration).

## Deviations from Plan

- **[Rule 3 - Blocking] Session cases in the real-app probe use `auth: "session_capable"`.** Found during Task 2: plain `session` cases got 401 because the route authenticates through `get_current_user_or_api_key`, which the probe overrides only for `api_key` / `session_capable`. Test-only change in `test_itam_cost_routes_enforced_on_real_app`; behavior asserted is the plan's.
- **Registry line spacing:** `_load(app, "itam_cost_endpoints", "router")` uses single spaces (not column-aligned with neighbours) so the plan's acceptance grep matches.

**Total deviations:** 2 minor, both test/format only. **Impact:** none on behavior.

## Authentication Gates

None.

## Known Stubs

None. `possibleDuplicatePairs` reads `possibleDuplicateOf` lists that 78-03 fills; it is 0 until then by design (plan-specified).

## Threat Flags

None beyond the plan's threat model (T-78-01..05 mitigated as specified: require_tenant, explicit tenantId filters, resolver, Owner-session-only override, guard mount, generic 500). The loader refusal tests and platform-admin ambient real-Mongo test are 78-09.

## Issues Encountered

None. Working tree carries the user's uncommitted mode change on `catalogue_mounts_assets.py` and `test_catalogue_slice_assets.py`; staged with `-c core.fileMode=false`, the commit carries no mode change.

## Verification

Plan-level command (cost endpoints, catalogue slice, route auth baseline, catalogue parity, KPIs, prebuilt reports, finance book value): 146 passed, 0 failed, 0 skipped.

## Next Phase Readiness

Ready for 78-02. 78-03 adds per-asset routes and fills `possibleDuplicateOf`; 78-04/78-05 refactor the KPI and Asset value report onto `itam_cost_service` and `resolve_itam_tenant`; 78-09 adds the golden-table and static-scan tests.

## Self-Check: PASSED

Files found: itam_cost_service.py, itam_tenant_scope.py, itam_cost_endpoints.py, test_itam_cost_endpoints.py. Commits 8fe9f982c, 7d220bcb8, 85e2f4dc3 present on branch npx.
