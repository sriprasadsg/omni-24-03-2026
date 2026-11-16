---
phase: 78-organization-endpoint-cost-api
plan: 03
subsystem: api
tags: [itam, cost, depreciation, pagination, tenant-isolation, fastapi, mongodb, agents]

requires:
  - phase: 78-organization-endpoint-cost-api
    provides: itam_cost_service computation, resolve_itam_tenant, cost summary route (78-01)
provides:
  - GET /api/itam/costs/assets: paged per-asset cost list with joined agent, includeDisposed and agentOnly
  - GET /api/itam/costs/assets/{id}: one asset's row (disposed included), identical 404 for unknown and foreign ids
  - itam_cost_service.load_agents_by_asset, mark_possible_duplicates, compute_asset_cost_detail, compute_tenant_costs(with_agents=)
affects: [78-04, 78-05, 78-08, 78-09, phase-80]

actuals:
  tokens: 10000
  tasks: 2
  commits: 4
plan_head_before: 56e32091c3010ff43c961d33083aca2654122956
plan_head_after: 887f0e3ea313ecc9c38f954efb3fbc116852da86

tech-stack:
  added: []
  patterns:
    - "Whole tenant set computed, sorted with a total order, then paged: no total depends on the page"
    - "Agent join only on agents.assetId from one tenant-scoped $in read; the asset's own agentStatus is never read"
    - "Duplicate serials are marked on both rows, never merged or dropped"

key-files:
  created:
    - backend/tests/test_itam_cost_assets.py
  modified:
    - backend/itam_cost_service.py
    - backend/itam_cost_endpoints.py

key-decisions:
  - "Duplicate pairs are formed among the raw documents of the rows in scope, so the default filter does not let a disposed hand-entered record mark an active agent asset (A-78-09)"
  - "The detail route computes the full tenant set (three reads) and returns one row, so its markers and agent equal the list row's (A-78-12)"
  - "possibleDuplicateOf is always present on rows from compute_tenant_costs ([] when unpaired), so the summary's pair count reads it for both routes"

patterns-established:
  - "compute_tenant_costs(with_agents=True) adds exactly one agents read; the default path keeps two reads, so the summary route is unchanged"

requirements-completed: [COST-03, COST-06, COST-07]

coverage:
  - id: D1
    description: "GET /api/itam/costs/assets lists every in-scope asset of the tenant (manual and agent-discovered) with cost, book value or reason and the joined agent, sorted and paged over the full set"
    requirement: COST-03
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_cost_assets.py#TestListTracer::test_list_tracer_real_mongo"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_cost_assets.py#TestPaging::test_page_walk_is_complete_and_stable"
        status: pass
    human_judgment: false
  - id: D2
    description: "List rows add up to the summary (count, purchase total, book value total), with and without includeDisposed"
    requirement: COST-06
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_cost_assets.py#TestListTracer::test_list_adds_up_to_summary"
        status: pass
    human_judgment: false
  - id: D3
    description: "Agent joined only via agents.assetId from one tenant-scoped read; latest lastSeen wins with agentCount; hostname-only match and foreign-tenant agents never join"
    requirement: COST-03
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_cost_assets.py#TestListTracer::test_two_agents_one_asset_single_row"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_cost_assets.py#TestListTracer::test_hostname_only_match_gets_no_agent"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_cost_assets.py#TestPaging::test_list_reads_each_collection_once"
        status: pass
    human_judgment: false
  - id: D4
    description: "Agent and hand-entered records with the same serial are both listed, both counted and marked possibleDuplicate; placeholders, uuid:/mac: keys and agent-agent pairs never match"
    requirement: COST-03
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_cost_assets.py#TestPossibleDuplicates"
        status: pass
    human_judgment: false
  - id: D5
    description: "Detail route returns the list row plus computedAt (disposed included) and one identical 404 body for unknown and foreign ids; guard and tenant resolver match the summary route"
    requirement: COST-07
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_cost_assets.py#TestDetail"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_cost_assets.py#test_cost_asset_routes_enforced_on_real_app"
        status: pass
    human_judgment: false

duration: 17min
completed: 2026-11-16
status: complete
---

# Phase 78 Plan 03: Per-asset cost list and detail Summary

**Paged per-asset cost list and detail routes that join agents only through agents.assetId, mark (never merge) agent/manual serial duplicates, and return rows that add up to the summary**

## Performance

- **Duration:** 17 min
- **Tasks:** 2 (tracer + duplicates/detail), each as RED then GREEN
- **Files:** 1 created, 2 modified

## Accomplishments

- `GET /api/itam/costs/assets` computes the whole tenant set, sorts it (valued by book value descending, not-tracked last, then name, tag, id), then pages; `page_size` is capped at 100 (422 above). Each request makes exactly one find on assets, asset_models and agents (counted in a test).
- An agent-discovered computer with no price is a row with `bookValueCents` null and reason `no_purchase_record`, its agent status taken from the agents document ("Offline"), not the asset's stale `agentStatus` ("Online").
- `mark_possible_duplicates` pairs `serial:<value>` hardware-keyed assets with hand-entered serials via `seat_identity.normalize_serial`; both keep their cost and both count; the summary's `possibleDuplicatePairs` and `coverage.flags.possibleDuplicate` now carry real numbers (they were 0 by design after 78-01).
- `GET /api/itam/costs/assets/{id}` returns the asset's row plus `computedAt`, disposed assets included, and the same `{"detail": "Asset not found"}` bytes for an unknown id and another tenant's id.

## Task Commits

1. Task 1 RED: `7368a709f` test(78-03) failing list-route tests (12 fail on 404)
2. Task 1 GREEN: `704b9dfd3` feat(78-03) agent join, list route, whole-set paging
3. Task 2 RED: `5bce4f53f` test(78-03) failing duplicate and detail tests (11 fail)
4. Task 2 GREEN: `887f0e3ea` feat(78-03) duplicate markers and detail route

## TDD Gate Compliance

Both RED commits precede their GREEN commits. Task 1's RED failed on `404 == 200` for every list test (the route did not exist), a target assertion on the planned status, not a load failure. Task 2's RED failed on missing `possibleDuplicateOf` / flags and on the detail route's 404 versus 200 and "Not Found" versus "Asset not found"; the two duplicate tests that expect no marker (`uuid_and_mac`, `two_agent_assets`) passed in RED because no marker existed yet, which is expected for negative cases. `workflow.tdd_mode` is false; the format classifier (`check tdd-red-evidence`) was not run.

Tracer gate: the Task 1 verify command was re-run after the commit (25 passed) before Task 2 started.

## Deviations from Plan

None - plan executed exactly as written. (The real-app probe uses `auth: "session_capable"` for the "nobody" session cases, following the 78-01 deviation, and API-key cases for `itam_viewer`.)

## Verification

- `backend/venv/bin/python -m pytest backend/tests/test_itam_cost_assets.py backend/tests/test_itam_cost_endpoints.py backend/tests/test_catalogue_slice_assets.py -q -p no:cacheprovider -rs`: 46 passed, 0 failed, 0 skipped.
- Also green: test_itam_reporting_kpis.py and test_itam_finance_bookvalue.py (74 passed with the cost suites).
- Acceptance greps: `def load_agents_by_asset` 1, `with_agents` 3, `le=100` 1, `paginate(` 1, `def mark_possible_duplicates` 1, `normalize_serial(` 2, `"/assets/{asset_id}"` 1, `Asset not found` 1. Line counts: service 336, endpoints 105, tests 358 (all under 500).

## Authentication Gates

None.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register: T-78-08 (identical 404, row from the tenant-scoped computation only), T-78-09 (one projected read per collection counted in a test, page_size capped; scale measurement is 78-08), T-78-10 (agents query carries an explicit tenantId; the tracer seeds a tenant-b agent naming a tenant-a asset and asserts it never appears) are mitigated as specified.

## Issues Encountered

None. The working tree carries the user's uncommitted mode change on `backend/tests/test_catalogue_slice_assets.py`; it was run but not edited or staged.

## Next Phase Readiness

Ready for 78-04 and 78-05 (KPI and Asset value report refactor onto `itam_cost_service`); the names and signatures they import are unchanged, `compute_tenant_costs` gained only a keyword-only `with_agents`. 78-08 measures the agents `$in` read at about 20k assets (A-78-11).

## Self-Check: PASSED

Files found: backend/tests/test_itam_cost_assets.py, backend/itam_cost_service.py, backend/itam_cost_endpoints.py. Commits 7368a709f, 704b9dfd3, 5bce4f53f, 887f0e3ea present on branch npx.
