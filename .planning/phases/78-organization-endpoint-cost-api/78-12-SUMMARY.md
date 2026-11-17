---
phase: 78-organization-endpoint-cost-api
plan: 12
subsystem: api
tags: [fastapi, multi-tenant, itam, custom-reports, tenant-isolation, mongodb, pytest]
gap_ids: [G-78-WR02]

requires:
  - phase: 78-organization-endpoint-cost-api
    provides: resolve_itam_tenant (78-05), real-middleware isolation pattern (78-07), D-13 amended 2026-11-17
provides:
  - all seven custom report routes (save, list, preview, get, delete, run, export) resolve one tenant through resolve_itam_tenant first
  - explicit tenantId in every itam_reports read, delete and insert
  - backend/tests/test_itam_custom_report_tenant.py, a 21-test two-tenant proof through the real middleware and real MongoDB
affects: [78-13, 78-14, 78-15, 78 security audit, 78 re-verification]

actuals:
  tokens: 6700
  tasks: 2
  commits: 4

tech-stack:
  added: []
  patterns:
    - "resolve_itam_tenant(request, current_user) as the first statement of every tenant-data handler, before get_database()"
    - "saved definitions follow the resolved tenant (A-78-22): tenantId in every itam_reports filter"

key-files:
  created:
    - backend/tests/test_itam_custom_report_tenant.py
  modified:
    - backend/itam_reporting_endpoints.py
    - backend/itam_tenant_scope.py

key-decisions:
  - "Saved-definition list, get, save and delete use the same resolver as run, preview and export (A-78-22): an Owner sees, saves into and deletes from the chosen tenant only; every custom route answers 400 without a tenant"
  - "In export_custom_report the resolver runs before the format check, matching export_prebuilt_report"
  - "No role widened (D-15): Support gets 400 on list/get and 403 elsewhere, Billing 403 on all seven, because the guards are untouched"

patterns-established:
  - "Two-tenant custom report tests seed the same model id with different policies in both tenants, which is what exposed the cross-tenant Book Value computation"

requirements-completed: [COST-07, COST-01]

coverage:
  - id: D1
    description: "All seven custom report routes take their one tenant from resolve_itam_tenant; a platform session without a chosen tenant (no header or platform-admin) gets 400 with no figure of either tenant"
    requirement: COST-07
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_custom_report_tenant.py#TestOwnerChoosesTenant::test_owner_without_a_real_tenant_is_400_everywhere"
        status: pass
    human_judgment: false
  - id: D2
    description: "An Owner with X-Tenant-ID gets only that tenant's rows, book values (with that tenant's own model policy), definitions, saves and export file/record"
    requirement: COST-07
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_custom_report_tenant.py#TestOwnerChoosesTenant"
        status: pass
    human_judgment: false
  - id: D3
    description: "Foreign and unknown definition ids give identical 404 bodies on get, run, export and delete; a refused delete leaves the document; tenant admins ignore X-Tenant-ID"
    requirement: COST-07
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_custom_report_tenant.py#TestForeignDefinitions, TestTenantUsersAndPlatformRoles::test_tenant_admin_header_spoof_is_ignored"
        status: pass
    human_judgment: false
  - id: D4
    description: "Platform Support gets 400 on list/get and 403 on the other five; Platform Billing gets 403 on all seven, with and without the header"
    requirement: COST-07
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_custom_report_tenant.py#TestTenantUsersAndPlatformRoles"
        status: pass
    human_judgment: false
  - id: D5
    description: "Ten rounds of eight concurrent custom run and list calls never mix tenants; the custom Book Value equals bookValueCents of GET /api/itam/costs/assets per tag"
    requirement: COST-01
    verification:
      - kind: integration
        ref: "backend/tests/test_itam_custom_report_tenant.py#TestConcurrencyAndParity"
        status: pass
    human_judgment: false

duration: 5min
completed: 2026-11-17
status: complete
plan_head_before: 05bbe5d7bea9ddd2d34c9aad67ef1ca6dd7202f8
plan_head_after: 8896830abde5d3036b1a171edc06670f17ed22d2
commits: 4
---

# Phase 78 Plan 12: Custom Report Tenant Resolution Summary

**All seven custom report routes now resolve a single tenant through the shared `resolve_itam_tenant`, closing the Owner blend (WR-02) including the Book Value column, proven by a 21-test two-tenant module through the real middleware and real MongoDB.**

## Performance

- **Duration:** 5 min measured from the recorded start (reading and planning before it are not counted)
- **Started:** 2026-11-17T07:22:26Z
- **Completed:** 2026-11-17T07:27:24Z
- **Tasks:** 2 (tracer + matrix), 4 task commits
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments

- A Platform Owner with no X-Tenant-ID, or with `platform-admin`, gets 400 "Select a tenant" on save, list, preview, get, delete, run and export, and no response carries an id, definition name or figure of either tenant.
- An Owner with X-Tenant-ID sees only that tenant's rows, definitions and export file; the Book Value column uses that tenant's own asset model policy although both tenants hold `model-std`. An Owner's save is stored under the chosen tenant (createdBy is the Owner's username) and appears in that tenant's shared list only; nothing is stored under `platform-admin`.
- Foreign and unknown definition ids produce byte-identical 404 bodies on get, run, export and delete, and a refused foreign delete leaves the document in place.
- No role was widened: Support 400 (list, get) or 403 (the rest), Billing 403 everywhere, tenant admins ignore X-Tenant-ID.
- Concurrency (10 rounds x 8 calls) and COST-01 parity with `GET /api/itam/costs/assets` hold for both tenants.

## Task Commits

1. **Task 1 (tracer): saved custom run covers the resolved tenant**
   - RED `79b6bfb9f` (test): 3 tests, 2 fail
   - GREEN `e25366d3a` (fix): `run_saved_custom_report` resolves the tenant first
2. **Task 2: the other six routes plus the full role matrix**
   - RED `fbea5fcec` (test): 21 tests, 10 fail
   - GREEN `8896830ab` (fix): save, list, preview, get, delete, export resolve the tenant first; docstrings updated

**Plan metadata:** the docs commit that follows this summary.

## RED evidence

- **Task 1 RED:** `test_owner_without_tenant_is_400` failed with `assert 200 == 400` (HEAD answered 200 and blended both tenants); `test_owner_with_tenant_runs_only_that_tenant` failed with `assert 4 == 2` (rowCount, both tenants' rows). `test_tenant_admin_runs_own_and_not_foreign_definition` passed already (wrapper scoping for tenant users), as expected. Both failures were on planned assertions, not import, fixture or seed errors (semantic assessment: target tests executed and failed for the intended reason). The `gsd_run check tdd-red-evidence` classifier was not run: the pytest console format is not one of its supported report formats, so the semantic inspection of the assertion output above is the evidence.
- **Task 2 RED (10 failed, 11 passed):** `test_owner_without_a_real_tenant_is_400_everywhere[None]` and `[platform-admin]` (save returned 201), `test_owner_with_tenant_covers_only_that_tenant[tenant-a|tenant-b]` (list returned both tenants' definitions), `test_owner_export_record_and_file_belong_to_the_chosen_tenant` (rowCount 4 not 2), `test_owner_save_lands_in_the_chosen_tenant_and_is_shared_there` (stored tenantId `platform-admin`), `test_foreign_and_unknown_ids_look_alike_and_nothing_is_deleted[owner]` (get answered 200 not 404), `test_support_gets_400_on_reads_and_403_on_the_rest[None|tenant-a]`, `test_concurrent_requests_do_not_mix`. All on assertions about the planned behaviour.

## Verification results

| Command | Result |
|---|---|
| `test_itam_custom_report_tenant.py` | 21 passed, 0 skipped |
| 4 reporting suites (cost_rules, builder, prebuilt, export) | 108 passed before the edit, 108 passed after, 0 skipped |
| 14-suite phase command + new module | 331 passed (310 + 21 new), 0 skipped, 108.7 s |

Acceptance greps: resolver call count 9, `request: Request` 9, `"tenantId": tenant_id` 6, resolver before the format check in export (1), `custom report` in itam_tenant_scope.py (1), resolver code below the imports byte-identical to before (cmp), endpoints 382 lines and test module 401 lines (both under 500), `test_itam_reporting_builder.py` and `test_itam_reporting_export.py` untouched (empty numstat).

## Leftover comparisons

- **omni_test_* databases:** listing before and after identical (no leftover).
- **backend/static/reports itam_report_* files:** the new module leaves none (autouse cleanup). The existing `test_itam_reporting_builder.py` and `test_itam_reporting_export.py` suites leave files behind on every run (rpt-1/rpt-pdf-1/rpt-xlsx-1 and warranty_expiring in csv/pdf/xlsx, 3 sets across my 3 runs of those suites); I removed exactly the files absent from the saved listing, and the listing now equals the one saved before the plan. This pre-existing leak is out of scope and not fixed.

## Files Created/Modified

- `backend/tests/test_itam_custom_report_tenant.py` - 21 tests, real TenantMiddleware, signed tokens, guards and MongoDB, two tenants with identical names, tags, serials and model id but different costs and policies
- `backend/itam_reporting_endpoints.py` - resolver first in seven custom handlers, tenantId in every itam_reports filter, module docstring paragraph
- `backend/itam_tenant_scope.py` - first docstring line only

## Decisions Made

Followed the plan (A-78-22): saved definitions follow the resolved tenant. The live database held no saved definitions, so nothing is orphaned or migrated.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking/convention] Removed the Co-Authored-By trailer from my first commit**
- **Found during:** Task 1 RED commit
- **Issue:** the harness attribution reminder asks for a trailer, but the project CLAUDE.md forbids one unless `.claude/settings.json` sets `attribution.commit`, which it does not; CLAUDE.md takes precedence.
- **Fix:** amended my own unpushed commit (`d5e289b03` became `79b6bfb9f`) and committed the rest without a trailer.
- **Files modified:** none beyond the commit message

**2. [Test structure] Task 1 test module was restructured in Task 2**
- The tracer tests were written with a bare `client.post` helper; Task 2 replaced it with the shared `call`/`Result` helpers and re-expressed the three tracer tests through them (same behaviours, same assertions). Task 1's RED/GREEN evidence above refers to the original form.

**Total deviations:** 2 (one commit-message convention fix, one test refactor). **Impact:** none on the code under test; no scope creep.

## Issues Encountered

None blocking. The pre-existing report-file leak of the builder and export suites is noted above.

## Known Stubs

None.

## Threat Flags

None. No new endpoint, auth path or schema; the existing routes were narrowed. T-78-29, T-78-30 and T-78-31 mitigations are in place and tested; T-78-32 (Owner fabricated X-Tenant-ID writes a definition under a nonexistent tenant) stays accepted per A-78-24 / IN-01.

## User Setup Required

None. Per the plan, no deploy, backend restart, UI publish or push was done; the new behaviour reaches the live backend only after the user's next restart. Note for that moment: the Reports tab will show 400 "Select a tenant" for an Owner without a chosen tenant until 78-14 updates the client.

## Next Phase Readiness

Server side of G-78-WR02 is closed. 78-13..15 (client request ordering, tenant argument removal on custom calls, platform-tier no-tenant state) can proceed, and the security audit and re-verification own 78-SECURITY.md, 78-VERIFICATION.md, 78-UAT.md and REQUIREMENTS.md statuses (not edited here).

## Self-Check: PASSED

- backend/tests/test_itam_custom_report_tenant.py, backend/itam_reporting_endpoints.py and backend/itam_tenant_scope.py exist.
- Commits 79b6bfb9f, e25366d3a, fbea5fcec and 8896830ab are on the branch; `git rev-list --count 05bbe5d7b..HEAD` printed 4.

---
*Phase: 78-organization-endpoint-cost-api*
*Completed: 2026-11-17*
