---
phase: 78-organization-endpoint-cost-api
plan: 07
subsystem: testing
tags: [itam, cost, tenant-isolation, middleware, session-tokens, rbac, mongodb, pytest]

requires:
  - phase: 78-organization-endpoint-cost-api
    provides: cost routes (78-01, 78-03), KPI route on the resolver (78-04), pre-built report run/export on the resolver (78-05)
provides:
  - "backend/tests/test_itam_cost_isolation.py: real Mongo, real TenantMiddleware, real signed session tokens, real guards and resolver, two tenants, all six routes"
  - "Owner-with-X-Tenant-ID regression (RESEARCH Pitfall 1) proven through the token-check tenant reset, not through overridden authentication"
affects: [78-09, 78-10, phase-80]

actuals:
  tokens: 5400
  tasks: 2
  commits: 2
plan_head_before: e512f5bab1baaca65fcbcb66eeb7cd2ec1d83d69
plan_head_after: 983bac25ce8583c46324e7083c8e80a5d0f98861

tech-stack:
  added: []
  patterns:
    - "Minimal FastAPI app = TenantMiddleware + the real routers; only the database accessors and the cost clock are patched"
    - "Leak check = foreign id fragments and dollar strings in the raw text plus foreign cents in the parsed leaves, so tiny numbers (seat counts) cannot cause false hits"
    - "Mutation check through a throwaway pytest plugin in the scratchpad that weakens the resolver in-process (never committed)"

key-files:
  created:
    - backend/tests/test_itam_cost_isolation.py
  modified: []

key-decisions:
  - "The permission check reads its role store from the same throwaway database (rbac_utils.get_database patched to the wrapper over mongo_db), so a role outside the built-in table (viewer) is refused on its merits, not because no database is connected"
  - "Foreign needles are asset-id fragments, agent ids, tenant names and formatted dollars; the cost, book value and total in cents are checked as parsed numbers"

requirements-completed: [COST-07]

coverage:
  - id: D1
    description: "A Platform Owner sending X-Tenant-ID gets only that tenant's exact figures from /costs/summary, /costs/assets, the detail route, /kpis and the Asset value report run and CSV export, through the real middleware and real authentication"
    requirement: COST-07
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_cost_isolation.py#TestOwnerSwitch::test_owner_header_reads_only_that_tenant"
        status: pass
      - kind: integration
        ref: "backend/tests/test_itam_cost_isolation.py#TestPlatformRoles::test_owner_header_reads_only_that_tenant_everywhere"
        status: pass
    human_judgment: false
  - id: D2
    description: "Tenant A never receives tenant B's figures, asset ids or tags on any of the six routes (and the swap), a foreign asset id answers the same 404 bytes as an unknown id, and a tenant admin's spoofed X-Tenant-ID is ignored"
    requirement: COST-07
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_cost_isolation.py#TestTenantIsolation (12 parametrized cases + 404 + spoof + viewer)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Owner with no tenant or with platform-admin gets 400 'Select a tenant' on all six routes; Support answers 400 on cost/KPI and 403 on pre-built run/export even with X-Tenant-ID; Billing answers 403 everywhere; no figure in any refused body"
    requirement: COST-07
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_cost_isolation.py#TestPlatformRoles"
        status: pass
    human_judgment: false
  - id: D4
    description: "Tenants holding assets with identical names, tags, serials and model ids stay separate; a possible-duplicate marker pairs only same-tenant assets"
    requirement: COST-07
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_cost_isolation.py#TestIdenticalLookingTenants"
        status: pass
    human_judgment: false
  - id: D5
    description: "Ten rounds of eight concurrent summary and KPI requests (tenant admins and the Owner with a header) each return only their own tenant's exact figures"
    requirement: COST-07
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_cost_isolation.py#TestConcurrency::test_concurrent_requests_do_not_mix"
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-11-16
status: complete
---

# Phase 78 Plan 07: Two-tenant isolation proof Summary

**A real-Mongo, real-TenantMiddleware, real-session-token isolation suite (29 tests) proving no cost, KPI or Asset value report figure crosses tenants, including the Platform Owner's X-Tenant-ID switch, Support, Billing and concurrent traffic**

## Performance

- **Duration:** about 25 min
- **Started/Completed:** 2026-11-16 (completed 21:20Z)
- **Tasks:** 2 (tracer + matrix)
- **Files:** 1 created (`backend/tests/test_itam_cost_isolation.py`, 413 lines)

## Accomplishments

- Authentication, the permission check, the route guards and `resolve_itam_tenant` all run for real; tokens come from `create_access_token`. The only patches are the database accessors (wrapped throwaway DB) and the cost clock. The module has 0 occurrences of the override and permission-patch identifiers.
- Seed: per tenant two priced assets plus one agent-discovered twin of the first (same serial, so it pairs inside its tenant), identical names, tags, serials and model id across tenants, different ids, costs (A 120000/54321, B 345600/87650), depreciation policy, seats (7 vs 30) and agent ids. A test asserts the shape of both tenants' asset documents really is identical.
- Matrix: six routes x both tenants (12 parametrized cases), swap-safe foreign-id 404 (byte-identical to the unknown-id 404), tenant-admin header spoof on every route, viewer 403, Owner no-tenant and `platform-admin` 400 on all six routes, Owner header on both tenants over all six routes, Support (400 cost/KPI, 403 run/export, with X-Tenant-ID), Billing 403 with and without the header, duplicate markers confined to a tenant, 10 gather rounds of 8 concurrent requests.
- Export files: read from `_REPORTS_DIR` then removed in a `finally`, plus an autouse fixture removing anything new; `git status --porcelain -- backend/static/reports` is identical before and after the run (5 pre-existing user lines).

## Mutation check (the tests can fail)

A throwaway pytest plugin (scratchpad, not committed) weakened the resolver in-process:

| Mutation | Result |
|----------|--------|
| resolver never writes the ambient tenant back | 2 failed (Owner header on every route; concurrency): the KPI licence/overdue reads fall to the token's tenant |
| resolver ignores X-Tenant-ID | 3 failed (Owner header tracer, matrix, concurrency) |
| platform context resolves to the sentinel instead of 400 | 7 failed |

## Task Commits

1. Task 1 (tracer): `bf66e0c54` test(78-07) Owner's X-Tenant-ID reads only that tenant through the real middleware (3 tests)
2. Task 2: `983bac25c` test(78-07) isolation matrix over every cost, KPI and Asset value report route (26 more tests)

## TDD Gate Compliance

This is a test-only plan over code landed in 78-01..78-05, so every test passed on first run and there is no RED or GREEN production commit. The tracer's verify command (3 passed, 0 skipped) was re-run after the commit before Task 2 began. `workflow.tdd_mode` is false; the RED classifier was not run. The mutation table above stands in for a RED run.

## Deviations from Plan

None - plan executed exactly as written. No production file needed a fix, so no cited fix commit exists. One addition inside the plan's spirit: `rbac_utils.get_database` is pointed at the throwaway database so the viewer case is refused by the real role store rather than by a "Database not connected" fail-closed path; the permission check itself is untouched.

## Verification

- `backend/venv/bin/python -m pytest backend/tests/test_itam_cost_isolation.py -q -p no:cacheprovider -rs`: 29 passed, 0 failed, 0 skipped.
- Acceptance: `add_middleware(TenantMiddleware)` 1, `create_access_token(` 1, `dependency_overrides` 0, permission-patch identifier 0, 12 parametrized isolation cases, module 413 lines (under 500), `backend/static/reports` status unchanged.
- No test process left running by this plan. A broad pytest run (PID 2831733) belongs to another session and was left alone.

## Authentication Gates

None.

## Known Stubs

None.

## Threat Flags

None. T-78-17 mitigated (throwaway DBs only, export files removed, reports status unchanged) and T-78-18 mitigated (concurrency rounds through the real middleware, mutation-checked).

## Issues Encountered

None. The working tree's roughly 2,300 uncommitted user files, including `backend/authentication_service.py`, were left alone; only the test module was staged by explicit path.

## Next Phase Readiness

Ready for 78-08, 78-09 and 78-10. The suite doubles as the COST-07 evidence for the phase verifier.

## Self-Check: PASSED

File found: backend/tests/test_itam_cost_isolation.py. Commits bf66e0c54 and 983bac25c present on branch npx.
