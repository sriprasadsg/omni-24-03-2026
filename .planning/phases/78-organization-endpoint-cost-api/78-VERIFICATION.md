---
phase: 78-organization-endpoint-cost-api
verified: 2026-11-17T13:15:00Z
status: passed
score: 13/13 must-haves verified
covered_files:
  - .planning/phases/78-organization-endpoint-cost-api/78-01-PLAN.md
  - .planning/phases/78-organization-endpoint-cost-api/78-01-SUMMARY.md
  - .planning/phases/78-organization-endpoint-cost-api/78-02-PLAN.md
  - .planning/phases/78-organization-endpoint-cost-api/78-02-SUMMARY.md
  - .planning/phases/78-organization-endpoint-cost-api/78-03-PLAN.md
  - .planning/phases/78-organization-endpoint-cost-api/78-03-SUMMARY.md
  - .planning/phases/78-organization-endpoint-cost-api/78-04-PLAN.md
  - .planning/phases/78-organization-endpoint-cost-api/78-04-SUMMARY.md
  - .planning/phases/78-organization-endpoint-cost-api/78-05-PLAN.md
  - .planning/phases/78-organization-endpoint-cost-api/78-05-SUMMARY.md
  - .planning/phases/78-organization-endpoint-cost-api/78-06-PLAN.md
  - .planning/phases/78-organization-endpoint-cost-api/78-06-SUMMARY.md
  - .planning/phases/78-organization-endpoint-cost-api/78-07-PLAN.md
  - .planning/phases/78-organization-endpoint-cost-api/78-07-SUMMARY.md
  - .planning/phases/78-organization-endpoint-cost-api/78-08-PLAN.md
  - .planning/phases/78-organization-endpoint-cost-api/78-08-SUMMARY.md
  - .planning/phases/78-organization-endpoint-cost-api/78-09-PLAN.md
  - .planning/phases/78-organization-endpoint-cost-api/78-09-SUMMARY.md
  - .planning/phases/78-organization-endpoint-cost-api/78-10-PLAN.md
  - .planning/phases/78-organization-endpoint-cost-api/78-10-SUMMARY.md
  - .planning/phases/78-organization-endpoint-cost-api/78-11-PLAN.md
  - .planning/phases/78-organization-endpoint-cost-api/78-11-SUMMARY.md
  - .planning/phases/78-organization-endpoint-cost-api/78-12-PLAN.md
  - .planning/phases/78-organization-endpoint-cost-api/78-12-SUMMARY.md
  - .planning/phases/78-organization-endpoint-cost-api/78-13-PLAN.md
  - .planning/phases/78-organization-endpoint-cost-api/78-13-SUMMARY.md
  - .planning/phases/78-organization-endpoint-cost-api/78-14-PLAN.md
  - .planning/phases/78-organization-endpoint-cost-api/78-14-SUMMARY.md
  - .planning/phases/78-organization-endpoint-cost-api/78-15-PLAN.md
  - .planning/phases/78-organization-endpoint-cost-api/78-15-SUMMARY.md
  - App.tsx
  - backend/itam_cost_endpoints.py
  - backend/itam_cost_service.py
  - backend/itam_finance_endpoints.py
  - backend/itam_finance_service.py
  - backend/itam_kpi_endpoints.py
  - backend/itam_reporting_endpoints.py
  - backend/itam_reporting_filters.py
  - backend/itam_reporting_kpis.py
  - backend/itam_reporting_prebuilt.py
  - backend/itam_tenant_scope.py
  - backend/tests/test_itam_cost_assets.py
  - backend/tests/test_itam_cost_endpoints.py
  - backend/tests/test_itam_cost_isolation.py
  - backend/tests/test_itam_cost_parity.py
  - backend/tests/test_itam_cost_service.py
  - backend/tests/test_itam_custom_report_tenant.py
  - backend/tests/test_itam_kpi_cost_rules.py
  - backend/tests/test_itam_report_cost_rules.py
  - components/itam/FinancePanel.tsx
  - components/itam/ITAMConsole.tsx
  - components/itam/ItamKpiPanel.tsx
  - components/itam/ReportResultView.tsx
  - components/itam/ReportsPanel.tsx
  - services/apiService.ts
  - src/__tests__/FinancePanel.test.tsx
  - src/__tests__/ITAMConsole.test.tsx
  - src/__tests__/ITAMKpiPanel.test.tsx
  - src/__tests__/ITAMReportsPanelStaleResponse.test.tsx
  - src/__tests__/ITAMReportsPanelTenantRule.test.tsx
covered_digest: "v3:sha256:19fa12c6f0aacedd959a3128e0e0ebeda410f92e4245aac1bcd853ced4fee03e"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: 10/10
  gaps_closed: []
  gaps_remaining: []
  regressions: []
---

# Phase 78: Organization & Endpoint Cost API Verification Report

**Phase Goal:** A tenant user with ITAM view access can read the organization's total asset cost and each endpoint's cost, computed by the same function that feeds the ITAM KPI tile, and can never see another tenant's numbers.
**Verified:** 2026-11-17T13:15:00Z
**Status:** passed
**Re-verification:** Yes, after the four code-review fix rounds (e828b2d0a..517b219c8, 8fcc59a69..042b9a814, 5700878cb + 78aff2770, 6b9351f63), deploy, and UAT completion (ce403172d)

## Verdict

The phase goal holds in committed HEAD (ce403172d). I read the shipped source, not the SUMMARYs, and ran the named test files myself: 315 backend tests and 141 frontend tests, all passing, none skipped. The previous report left one item at `human_needed` (the post-deploy live check). The user has since deployed and recorded that item as `pass` in 78-UAT.md. What that pass did and did not observe is stated below; I treat the item as resolved, with the residual noted, so the status is `passed`.

The user's uncommitted work-in-progress (App.tsx, services/apiService.ts, components/itam/ReportsPanel.tsx, src/__tests__/ITAMConsole.test.tsx, src/__tests__/ITAMReportsPanel.test.tsx, backend/itam_models.py and others) is not part of the verdict. I did not edit, stage or restore any source file. The backend files I read for the goal (`itam_cost_service.py`, `itam_cost_endpoints.py`, `itam_tenant_scope.py`, `itam_reporting_endpoints.py`, `itam_finance_endpoints.py`, `itam_reporting_kpis.py`, `itam_reporting_prebuilt.py`) have no working-tree diff. The frontend vitest run did execute against the working tree, which includes that WIP; the frontend files carrying WIP were checked against `git show HEAD:<path>` for the symbols that matter (see Key Links).

## What was and was not observed live

Source: 78-UAT.md test 1, `result: pass`, with the note recorded at ce403172d.

Observed live (nginx access log since the 11:02 deploy, one client, new UI bundle `index-B6_i-liT.js` loaded three times):
- Platform Owner session, only GET requests, all 200: `/api/itam/kpis` (the KPI tile), `/api/itam/reports`, `/api/itam/reports/custom`, `/api/itam/settings`, catalog and license lists, and `/api/assets/asset-EILT0197/book-value`. No 400 was returned.

Not observed live (rests on automated tests only):
- Report run, preview, save, export and delete.
- A tenant switch in the middle of a run or an export.
- Platform Support with no tenant (no Support account exists on this server).
- A real two-tenant cross-read against the live database. Cross-tenant isolation was proven only by the test database runs, not on the deployed system.

I did not hit the live system myself and did not touch the live `omni_platform` database. The user chose to record `pass` with this note, and the automated coverage for the unobserved paths is described under the truths below. If a stricter standard than "user accepted the UAT" is wanted, the unobserved items are the ones to exercise next.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `GET /api/itam/costs/summary` returns purchase total, book value total and coverage; assets without cost data are null, never 0 | VERIFIED | `itam_cost_service._total` returns `{cents: None, hasData: False}` when nothing contributes; `compute_asset_cost` writes `None` for unreadable or missing cost. Route at `itam_cost_endpoints.py:28-52`. `test_itam_cost_service.py` (golden table) and `test_itam_cost_endpoints.py` pass |
| 2 | `/costs/assets` (paged, whole-set sort) and `/costs/assets/{id}` return per-asset cost and book value, agent endpoints joined only via `agents.assetId` | VERIFIED | `load_agents_by_asset` queries `{"tenantId":..., "assetId": {"$in": ids}}` only; no hostname or `agentStatus` read. Detail route returns the same row as the list. `test_itam_cost_assets.py` 26 passed |
| 3 | KPI tile, Asset value report and cost summary show identical figures for a tenant through one shared per-asset computation, parity-tested | VERIFIED | `itam_reporting_kpis.py:88`, `itam_reporting_prebuilt.py:131` and `itam_reporting_filters.py:279` all call `compute_asset_cost`; the cost service calls the same function. `test_itam_cost_parity.py` 9 passed, including the golden table with an `N-SALVAGE` case |
| 4 | Disposed and retired assets are excluded from current book value by default and counted in historical purchase totals only behind an explicit filter, same rule in KPI and cost view | VERIFIED | One `INACTIVE_STATUSES` set and one `normalize_lifecycle_status` imported by cost service, KPI module and the pre-built report (IN-02). `test_itam_kpi_cost_rules.py` (13) and `test_itam_report_cost_rules.py` (18) pass |
| 5 | Every cost route: 403 without `view:itam`, 400 for a platform-admin or no-tenant context, two-tenant isolation proves A never sees B | VERIFIED | All three cost routes depend on `_require_itam_viewer` (view:itam or manage:assets, then API-key scope) and call `resolve_itam_tenant` before any DB read. `test_itam_cost_isolation.py` 29 passed through the real middleware |
| 6 | After a tenant switch the Reports tab shows no previous-tenant title, rows or export, including a late response | VERIFIED | `runSeq`/`tenantEpoch` guards in HEAD `ReportsPanel.tsx`; `ITAMReportsPanelStaleResponse.test.tsx` passes |
| 7 | All seven custom report routes and the custom client calls follow the one-tenant rule (WR-02) | VERIFIED | `resolve_itam_tenant` is the first statement in each custom handler (`itam_reporting_endpoints.py` lines 236, 261, 280, 294, 308, 327, 355). `test_itam_custom_report_tenant.py` 23 passed; `ITAMReportsPanelTenantRule.test.tsx` passes |
| 8 | The shown report, its title, export target and pages always belong together (WR-04) | VERIFIED | `shown` held as one value, behavioural tests for failed and superseded runs pass |
| 9 | An export never downloads or toasts for a previous tenant (IN-05) | VERIFIED | `tenantEpoch` captured at click time in `handleExport`; named tests pass |
| 10 | Every platform tier without a tenant is blocked on the client; a server "Select a tenant" 400 enters the same state without a toast (IN-04) | VERIFIED | HEAD `ITAMConsole.tsx:85` `needsTenant = isPlatformView && !tenantId`; `takeTenantRejection` in every catch; tests pass |
| 11 | New contract: `resolve_itam_tenant` is async; an Owner `X-Tenant-ID` naming an unknown or partner tenant gets 400, and the client treats it as a blocked state | VERIFIED | `itam_tenant_scope.py`: `await get_db().tenants.find_one({"id": tenant_id, "type": {"$ne": "partner"}}, ...)` runs only for the Owner header case, then `UNKNOWN_TENANT_DETAIL` 400. Backend tests `test_owner_header_for_an_unknown_tenant_is_400_on_read_and_write_routes` and `test_owner_header_for_a_partner_organization_is_400_like_an_unknown_tenant` pass, the latter also asserting no `itam_reports` document is written under the partner id and the cost route refuses it. Frontend: `SELECT_TENANT_RE = /^(Select a tenant\|Unknown tenant)/i` in `ItamKpiPanel.tsx` (IN-11); KPI and Reports tests pass |
| 12 | New contract: salvage above purchase cost yields `salvage_exceeds_cost` on the cost row and on the per-asset book-value route alike (parity) | VERIFIED | One `policy_misfit_reason` is called by `compute_asset_cost` and by `itam_finance_endpoints.py:170`; the book-value route also reports `unreadable_purchase_cost` and echoes `purchaseCostCents` only when readable (WR-07, WR-08). `test_itam_cost_parity.py` compares route and row reasons for every unvalued asset (IN-14); `test_itam_cost_service.py::test_salvage_above_cost_is_marked_not_valued` passes |
| 13 | New contract: duplicate markers are computed over all tenant assets, then scoped, so a row carries the same markers with or without `includeDisposed` and the detail row equals the list row (WR-03) | VERIFIED | `compute_tenant_costs` calls `mark_possible_duplicates(assets)` on the full asset list before filtering to in-scope rows; `compute_asset_cost_detail` reuses it. `test_serial_duplicate_pair_marked` and `test_detail_carries_duplicate_markers` pass |

**Score:** 13/13 truths verified (0 present-but-behavior-unverified). Truths 6 to 11 are behaviour-dependent (ordering, cancellation, cleanup, refusal ahead of a read); each is backed by a passing named test that exercises the transition against the real middleware or a held request, not by symbol presence.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/itam_cost_service.py` | The one per-asset computation | VERIFIED | 363 lines, pure, no web-framework import, `require_tenant` guard, no `$lookup`, no cache |
| `backend/itam_cost_endpoints.py` | summary, assets, assets/{id} | VERIFIED | 105 lines; mounted through `router_registry.py:121` with the ITAM API-key guard in `catalogue_mounts_assets.py:56` |
| `backend/itam_tenant_scope.py` | Async shared resolver | VERIFIED | Owner-session-only header choice, existence and non-partner check, writes ambient tenant back |
| `backend/itam_reporting_endpoints.py` | Custom report routes on the resolver | VERIFIED | Resolver first in all seven handlers |
| `backend/itam_finance_endpoints.py` | Book-value route sharing the policy check | VERIFIED | `policy_misfit_reason`, `is_cents`, unreadable reasons imported from the cost service |
| `components/itam/ReportsPanel.tsx`, `ReportResultView.tsx`, `ITAMConsole.tsx`, `ItamKpiPanel.tsx`, `services/apiService.ts` | Tenant-following UI | VERIFIED | Present and wired at HEAD; trailing `tenantId` on the custom client calls |
| `backend/tests/test_itam_cost_isolation.py`, `test_itam_custom_report_tenant.py`, `test_itam_cost_parity.py` | Mandatory two-tenant, parity tests | VERIFIED | 29, 23 and 9 tests, all pass |

### Key Link Verification

| From | To | Via | Status |
|------|----|-----|--------|
| cost routes, KPI route, pre-built and custom report routes | `resolve_itam_tenant` | awaited first in each handler | WIRED |
| KPI tile, Asset value report, custom Book Value column, cost routes | `compute_asset_cost` | direct import and call | WIRED |
| Book-value route | `policy_misfit_reason` | import and call at `itam_finance_endpoints.py:170` | WIRED |
| `ITAMConsole` | `ItamKpiPanel` / `ReportsPanel` | `tenantId`, `needsTenant` props (HEAD lines 148-149) | WIRED |
| ReportsPanel catches | `SELECT_TENANT_RE` / `takeTenantRejection` | `blocked = needsTenant \|\| tenantRejected` (HEAD) | WIRED |
| ReportsPanel | `ReportResultView` | one `shown` value | WIRED |
| Cost router | app | `router_registry.py:121` plus ITAM API-key guard mount | WIRED |

### Data-Flow Trace (Level 4)

| Artifact | Data variable | Source | Real data | Status |
|----------|---------------|--------|-----------|--------|
| cost routes | `rows`, `summary` | `db.assets.find({"tenantId": ...})`, `db.asset_models.find(...)`, `db.agents.find(...)` | yes (test database) | FLOWING |
| KPI tile and Asset value report | per-asset rows | the same `compute_asset_cost` over the same tenant-filtered read | yes | FLOWING |
| ReportResultView | `shown.data` | tenant-resolved report routes | yes | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Cost, custom report, parity, isolation, KPI and report rules | `backend/venv/bin/python -m pytest` on `test_itam_custom_report_tenant.py`, `test_itam_cost_isolation.py`, `test_itam_cost_parity.py`, `test_itam_cost_endpoints.py`, `test_itam_cost_service.py`, `test_itam_cost_assets.py`, `test_itam_kpi_cost_rules.py`, `test_itam_report_cost_rules.py` | 206 passed in 28.9 s | PASS |
| Book-value route, KPI, pre-built and builder reports | `pytest` on `test_itam_finance_bookvalue.py`, `test_itam_reporting_kpis.py`, `test_itam_reporting_prebuilt.py`, `test_itam_reporting_builder.py` | 109 passed | PASS |
| Reports, console, KPI and Finance frontend | `npx vitest run` on ITAMReportsPanelStaleResponse, ITAMReportsPanelTenantRule, ITAMReportsPanel, ITAMConsole, ITAMKpiPanel, FinancePanel | 6 files, 141 passed (working tree, includes the user's WIP) | PASS |
| Full backend phase command, full vitest, build, Nyquist, security | run by the orchestrator on 2026-11-17 (410 passed 0 skipped; 136 files 2,295 passed; 0 validation gaps; 42/42 threats closed) | not re-run by me | accepted as reported |

I did not run the full backend suite or a broad `-k` selection, per the instruction.

### Probe Execution

Step 7c: SKIPPED (the phase declares no probe scripts).

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|--------------|-------------|--------|----------|
| COST-01 | 78-01, 78-04, 78-05, 78-08, 78-09, 78-10, 78-12 | Same per-asset computation as the KPI tile, parity-tested | SATISFIED | Truths 3, 12 |
| COST-02 | 78-01, 78-02, 78-09, 78-10 | Org summary with coverage, null never 0 | SATISFIED | Truth 1 |
| COST-03 | 78-03, 78-10 | Per-asset cost list and detail via `agents.assetId` | SATISFIED | Truths 2, 13 |
| COST-06 | 78-04, 78-05, 78-08, 78-09, 78-10 | Disposed/retired rule across KPI and cost view | SATISFIED | Truth 4 |
| COST-07 | 78-01, 78-06, 78-07, 78-08, 78-10 to 78-15 | Explicit tenant on every route, no `$lookup` or cache, two-tenant isolation | SATISFIED | Truths 5 to 11 |

All five IDs appear in plan frontmatter and in REQUIREMENTS.md. No orphaned requirement (COST-04 and COST-05 belong to Phase 79, COST-08 to Phase 80). REQUIREMENTS.md still lists COST-01, 02, 03, 06 and 07 as "Gaps Found" from the earlier revert (lines 197-203) and the checkboxes at lines 152-158 are unchecked. Flipping these is the orchestrator's completion step; I did not edit it.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| all phase source files | - | TBD/FIXME/XXX/TODO/HACK scan on the seven backend modules and the five frontend files (HEAD content) | none | clean |
| `backend/itam_finance_endpoints.py` | 157 | IN-15 (open, recorded in 78-REVIEW-DISPOSITION.md): the book-value route echoes `purchaseDate` raw while the cost row sanitizes a non-string one; no consumer reads it | Info | Does not affect any figure or any tenant boundary |
| `backend/itam_finance_endpoints.py` | 141 | The per-asset book-value route reads `current_user.tenant_id` and relies on the auto-scoped DB wrapper rather than `resolve_itam_tenant` | Info | Pre-Phase-78 Finance route, outside the phase's cost routes; an unknown or foreign id gives the same 404, so no cross-tenant read. Not a goal gap |
| `components/itam/ReportsPanel.tsx` | 56-67 | A Support user with a selected tenant reaches the no-tenant state only after the first rejected request, because the client cannot know the server ignores the header | Info | By design (A-78-39) |

The IN-01 anti-pattern that the previous report listed as open (an Owner's fabricated `X-Tenant-ID` accepted for writes) is now closed by the unknown-or-partner-tenant 400 (truth 11).

### Human Verification Required

None outstanding. The one item from the previous report (the post-deploy live check) is recorded `pass` in 78-UAT.md. See "What was and was not observed live" for the exact scope of that pass; the unobserved paths are covered by the passing automated suites listed above.

### Gaps Summary

None. The five ROADMAP success criteria, the earlier gap-round truths and the three contract changes from the review-fix rounds hold in committed HEAD and are proven by passing behavioural tests. The 23 review findings are 22 fixed and 1 open (IN-15, info). The only thing short of live proof is the set of paths listed as not observed live, which rest on automated tests.

---

_Verified: 2026-11-17T13:15:00Z_
_Verifier: Claude (gsd-verifier)_
