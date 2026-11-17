---
phase: 78-organization-endpoint-cost-api
verified: 2026-11-17T09:00:00Z
status: human_needed
score: 10/10 must-haves verified
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
  - backend/itam_reporting_endpoints.py
  - backend/itam_tenant_scope.py
  - backend/tests/test_itam_custom_report_tenant.py
  - components/itam/ITAMConsole.tsx
  - components/itam/ItamKpiPanel.tsx
  - components/itam/ReportResultView.tsx
  - components/itam/ReportsPanel.tsx
  - services/apiService.ts
  - src/__tests__/ITAMConsole.test.tsx
  - src/__tests__/ITAMReportsPanelStaleResponse.test.tsx
  - src/__tests__/ITAMReportsPanelTenantRule.test.tsx
covered_digest: "v3:sha256:bbc6994704b8fdbf75914a9ffa96656b4872eeb328a97c33b859ee51a97300df"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: 6/6
  gaps_closed:
    - "G-78-WR02: every custom report route resolves one tenant (server, 78-12) and every custom client call carries the selected tenant (client, 78-14)"
    - "G-78-WR04: ReportsPanel keeps the shown report and its identity as one value (78-13)"
    - "G-78-IN05: an export started in one tenant neither downloads nor toasts after a tenant switch (78-13)"
    - "G-78-IN04: every platform tier without a tenant is needsTenant, and a 'Select a tenant' rejection puts the Reports tab into the no-tenant state (78-15)"
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "After the user deploys this round (backend restart for 78-12, UI publish for 78-13..15, push), a Platform Owner opens ITAM with a tenant selected, then with none; a Platform Support user opens ITAM with none."
    expected: "Owner with a tenant: KPI tile shows 'Not tracked' or a dollar value and 'Valued X of Y'; Reports tab runs, previews, saves, exports and deletes act on that tenant only, and the saved list shows only that tenant's definitions. Owner with no tenant: Select-a-tenant block, every pre-built Run disabled with the pre-built note, custom section disabled with the custom note, no request and no error toast. Support with no tenant: same no-tenant state. Switching tenant mid-run or mid-export leaves no previous-tenant table, list, download or toast. After a failed run the earlier report keeps its title, rows, export target and pages."
    why_human: "Live rendering and a real session on the deployed system. The live backend still runs the pre-78-12 code and the published UI predates 78-13, so none of this round is live; deploy, publish and push belong to the user. This is the one Manual-Only row in 78-VALIDATION.md and the pending test 1 in 78-UAT.md. No code gap is implied."
---

# Phase 78: Organization & Endpoint Cost API Verification Report

**Phase Goal:** A tenant user with ITAM view access can read the organization's total asset cost and each endpoint's cost, computed by the same function that feeds the ITAM KPI tile, and can never see another tenant's numbers.
**Verified:** 2026-11-17T09:00:00Z
**Status:** human_needed
**Re-verification:** Yes, after gap-closure round 2 (plans 78-12..78-15)

## Verdict

All four gaps recorded in 78-UAT.md are closed in committed HEAD, and nothing from the earlier verification regressed. I read the committed source (`git show HEAD:<path>` for the four files that carry the user's uncommitted edits), ran the new and neighbouring tests myself, and found no failing must-have and no blocker. The status is `human_needed` only because the one post-deploy live check remains and this round is not deployed. That is a user action, not a code gap.

The user's uncommitted work is not part of the verdict. `git diff` shows the working-tree changes in `components/itam/ReportsPanel.tsx` (one deleted lint-suppression comment), `services/apiService.ts` (a new `setUserPassword`), `App.tsx` (unrelated hunks; the `isPlatformView` prop line is already in HEAD) and the two test files are the user's own and unrelated to the gap work. I did not edit, stage or restore any source file.

## Gap closure, one by one

### G-78-WR02 (custom report routes tenant rule): CLOSED, server and client

Server (78-12), `backend/itam_reporting_endpoints.py` (identical to HEAD, no working-tree diff):
- `resolve_itam_tenant(request, current_user)` is the first statement of all seven custom handlers (save line 236, list 261, preview 280, get 294, delete 308, run 327, export 355), before `get_database()`.
- Every `itam_reports` read and write is filtered on the resolved `tenantId` (list, get, delete, run, export lookups, and the save document); `build_report_rows` and the export `generate` receive the resolved tenant.
- `backend/itam_tenant_scope.py` is unchanged since the prior verification except the docstring naming the custom routes.
- I ran `test_itam_custom_report_tenant.py` plus `test_itam_cost_isolation.py`: 50 passed. The custom module (21 tests, real `TenantMiddleware`, signed tokens, real MongoDB) asserts: Owner with no header or `platform-admin` gets 400 starting "Select a tenant" on all seven routes with no figure leaked and no document changed; Owner with a tenant gets only that tenant's rows, definitions, export file and export record; foreign and unknown ids give byte-identical 404 bodies and a refused foreign delete leaves the document; a tenant admin's spoofed `X-Tenant-ID` is ignored on every route; Platform Support gets 400 on list/get and 403 elsewhere; Billing 403 everywhere; ten concurrent rounds of four actors never mix; the custom Book Value column equals `bookValueCents` from `/api/itam/costs/assets` per tenant (COST-01 parity).
- No new file appeared in `backend/static/reports` after my run (listing compared before and after).

Client (78-14), `services/apiService.ts` at HEAD: `listItamCustomReports`, `saveItamCustomReport`, `deleteItamCustomReport`, `previewItamCustomReport` and `runItamCustomReport` all take a trailing `tenantId` and pass `tenantId: tenantId || undefined` to `authFetch`, which writes `X-Tenant-ID` (line 317). `ReportsPanel` HEAD passes `tenantId` on every one of them and on `generateItamReport`. Under `needsTenant` the saved list is not fetched (`loadSavedReports` early return), the builder is hidden (`builderOpen && !blocked`) and Create Custom Report is disabled with the custom note. A `listSeq` guard drops a stale list response, and the switch effect clears the list and any open delete. Save and delete are guarded by `tenantEpoch`. `ITAMReportsPanelTenantRule.test.tsx` (16 tests, committed) pins the transport header with and without a tenant for all five functions, the stale-list drop, the save/delete-after-switch silence and the no-tenant section.

### G-78-WR04 (shown report and its identity): CLOSED

`ReportsPanel` HEAD holds `shown: {kind, key, page, data}` as one state value, written only after the `runSeq` check; the run in flight is a separate `pending`. `ReportResultView` (129 lines, ReportsPanel 368, both under their caps) derives title, export buttons, export target (`const { kind, key } = shown` at click time) and page controls from `shown`; while a run is in flight it shows the pending title with Loading and hides export and paging. A failed run never writes `shown`, so the earlier report keeps its title, rows, export target and pages; a preview that supersedes an in-flight run bumps `runSeq`, clears `pending`, and a failed preview leaves `shown` untouched. Named tests in `ITAMReportsPanelStaleResponse.test.tsx` (all passing): "a failed run after a successful one keeps the earlier report's title, rows and export target", "a builder preview that supersedes an in-flight run and fails keeps the earlier report and its export target", "pagination follows the shown report after a failed run", "an in-flight run shows its own title and no export buttons". The 78-11 render gate (`resultIsCurrent`) is gone and its behaviours remain pinned by the earlier tests, which still pass unedited.

### G-78-IN05 (export across a tenant switch): CLOSED

`handleExport` captures `tenantEpoch.current` at click time and, after the generate and after the download, returns without a download, toast or state write if the epoch moved; `exportingFormat` is cleared only for the current epoch and reset in the tenant-change effect. The epoch moves on tenant switch only, so a same-tenant new run does not cancel an export. Tests: "an export started before a tenant switch neither downloads nor keeps the buttons disabled", "an export that fails after a tenant switch raises no toast", "an export in the same tenant still downloads when a new run starts" all pass.

### G-78-IN04 (every platform tier is "needs a tenant"): CLOSED

`ITAMConsole.tsx` HEAD: `needsTenant = (isSuperAdminView || isPlatformView) && !tenantId` and an `isPlatformView` prop; `App.tsx` passes `isPlatformView={isPlatformRoleName(currentUser.role)}`. `ItamKpiPanel` exports `SELECT_TENANT_RE` and `ReportsPanel` imports it; `takeTenantRejection` sets `tenantRejected` (matched, never rendered) in the saved-list, pre-built run, saved run and export catches, so a Support user with a selected tenant that the server ignores lands in the no-tenant state instead of a toast; `blocked = needsTenant || tenantRejected` gates every Reports control and a tenant change clears it. Tests (all pass): Support with no tenant gets the Select block with no request or toast; Billing is refused by `evaluateViewAccess` while Support is allowed; list, run and export rejections each enter the no-tenant state without a toast; another rejection still toasts; a tenant change clears the rejected state. No server check was relaxed: `itam_tenant_scope.py` and the guards are unchanged.

## Goal Achievement

### Observable Truths

ROADMAP success criteria 1-5 and the 78-06 truth carry over from the prior verification; the four gap truths are new.

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `GET /api/itam/costs/summary` returns purchase total + book value total + coverage; no-cost assets null, never 0 | VERIFIED (regression check) | Cost backend files have no diff against HEAD; `test_itam_cost_service.py`, `test_itam_cost_endpoints.py` pass in my 144-test run |
| 2 | `/costs/assets` (paginated) and `/costs/assets/{id}` return per-asset purchase cost and book value, agent endpoints via `agents.assetId` | VERIFIED (regression check) | `test_itam_cost_assets.py` passes |
| 3 | KPI tile, Asset value report and cost summary show identical figures for a tenant, via one shared per-asset computation, parity-tested | VERIFIED (regression check) | `test_itam_cost_parity.py` passes; the custom report is now also parity-checked per tenant (`test_custom_book_value_equals_the_cost_list`) |
| 4 | Disposed/retired excluded from current book value by default, counted in historical purchase totals only behind an explicit filter, same rule in KPI and cost view | VERIFIED (regression check) | `test_itam_kpi_cost_rules.py`, `test_itam_report_cost_rules.py` pass |
| 5 | Every cost route: 403 without `view:itam`, 400 for platform-admin/no tenant, two-tenant isolation proves A never sees B | VERIFIED (regression check) | `test_itam_cost_isolation.py` 29 passed through the real middleware |
| 6 | 78-06: after a tenant switch ReportsPanel shows no previous-tenant title, rows or export, including a late response | VERIFIED | `runSeq` guard retained on all writers; `shown` cleared in the switch effect; stale tests pass |
| 7 | G-78-WR02: all seven custom report routes and all custom client calls follow the one-tenant rule | VERIFIED | See gap section; 21 backend and 16+ frontend tests pass; handler order and filters read in source |
| 8 | G-78-WR04: shown report, title, export target and pages always belong together; a failed or superseded run leaves the earlier consistent report | VERIFIED | See gap section; named behavioural tests pass |
| 9 | G-78-IN05: an export never downloads or toasts for a previous tenant, and the switch resets the exporting state | VERIFIED | See gap section; named behavioural tests pass |
| 10 | G-78-IN04: every platform tier without a tenant is blocked on the client and a server "Select a tenant" 400 puts the Reports tab into the same state without a toast | VERIFIED | See gap section; named behavioural tests pass |

**Score:** 10/10 truths verified (0 present-but-behavior-unverified). Truths 6 to 10 are behaviour-dependent (ordering, cancellation, cleanup); each is backed by a passing named test that holds a request across the transition, not by symbol presence.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/itam_reporting_endpoints.py` | resolver first in all seven custom handlers, tenantId in every `itam_reports` filter | VERIFIED | Matches HEAD; read in full |
| `backend/itam_tenant_scope.py` | resolver, docstring names custom routes | VERIFIED | Unchanged logic |
| `backend/tests/test_itam_custom_report_tenant.py` | two-tenant proof through the real middleware | VERIFIED | 401 lines, 21 tests, pass |
| `components/itam/ReportResultView.tsx` | one `ShownReport`-driven result area | VERIFIED | 129 lines, wired from ReportsPanel |
| `components/itam/ReportsPanel.tsx` | `shown`/`pending`, `tenantEpoch`, `listSeq`, `blocked` | VERIFIED | 368 lines at HEAD |
| `services/apiService.ts` | trailing `tenantId` on five custom functions | VERIFIED | At HEAD |
| `components/itam/ITAMConsole.tsx`, `App.tsx` | `isPlatformView` prop and `needsTenant` rule | VERIFIED | At HEAD |
| `components/itam/ItamKpiPanel.tsx` | `export const SELECT_TENANT_RE`, `customReportsSelectTenantNote` | VERIFIED | Imported by ReportsPanel |
| `src/__tests__/ITAMReportsPanelTenantRule.test.tsx` | transport and no-tenant tests | VERIFIED | Committed, passes |

### Key Link Verification

| From | To | Via | Status |
|------|----|-----|--------|
| custom handlers | `resolve_itam_tenant` | first statement of every handler | WIRED |
| `resolve_itam_tenant` | `tenant_context.set_tenant_id` | scopes wrapper reads for run_custom_report | WIRED (tests prove no cross-tenant rows, including same-id asset models with different policies) |
| `runSavedCustom` | `runItamCustomReport(reportId, targetPage, PAGE_SIZE, tenantId)` | trailing tenant | WIRED |
| `loadSavedReports` | `listItamCustomReports(tenantId)` | `listSeq` guarded, skipped under `needsTenant` | WIRED |
| `handleExport` | `generateItamReport(kind, key, format, tenantId)` | kind and key from `shown` at click time | WIRED |
| tenant-change effect | `tenantEpoch`, `runSeq` | both bumped | WIRED |
| `ReportsPanel` | `ReportResultView` | one `shown` value | WIRED |
| `App.tsx` itam case | `ITAMConsole needsTenant` | `isPlatformView={isPlatformRoleName(currentUser.role)}` | WIRED |
| ReportsPanel catches | `SELECT_TENANT_RE` | `takeTenantRejection(e)` | WIRED |

### Data-Flow Trace (Level 4)

| Artifact | Data variable | Source | Real data | Status |
|----------|---------------|--------|-----------|--------|
| `ReportResultView` | `shown.data` | `runItamPrebuiltReport` / `runItamCustomReport` / `previewItamCustomReport` responses from tenant-resolved backend routes backed by `build_report_rows` and `compute_asset_cost` | yes | FLOWING |
| `ReportsPanel` saved list | `savedReports` | `listItamCustomReports(tenantId)` to `itam_reports.find({"tenantId": tenant_id})` | yes | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Custom report tenant rule and cost isolation | `backend/venv/bin/python -m pytest tests/test_itam_custom_report_tenant.py tests/test_itam_cost_isolation.py -q -p no:cacheprovider` | 50 passed | PASS |
| Cost regression suites | `pytest tests/test_itam_cost_parity.py test_itam_cost_endpoints.py test_itam_cost_service.py test_itam_cost_assets.py test_itam_kpi_cost_rules.py test_itam_report_cost_rules.py -q -p no:cacheprovider` | 144 passed | PASS |
| Reports/console/KPI frontend suites | `npx vitest run` on ITAMReportsPanelStaleResponse, ITAMReportsPanelTenantRule, ITAMReportsPanel, ITAMConsole, ITAMKpiPanel | 5 files, 121 passed | PASS |
| No leaked export files | listing of `backend/static/reports` before and after | no new file | PASS |
| Full backend phase command, full vitest, build, validation, security, review | run by the orchestrator (331 passed 0 skipped; 136 files 2,278 passed; build exit 0; 0 validation gaps; 42/42 threats; review 0 critical 0 warning) | not re-run by me | accepted as reported |

### Probe Execution

Step 7c: SKIPPED (the phase declares no probe scripts).

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|--------------|-------------|--------|----------|
| COST-01 | 78-01, 78-04, 78-05, 78-08, 78-09, 78-10, 78-12 | Same per-asset computation as the KPI tile, parity-tested | SATISFIED | Truth 3; custom report now parity-tested per tenant |
| COST-02 | 78-01, 78-02, 78-09, 78-10 | Org summary with coverage, null never 0 | SATISFIED | Truth 1 |
| COST-03 | 78-03, 78-10 | Per-asset cost list and detail via `agents.assetId` | SATISFIED | Truth 2 |
| COST-06 | 78-04, 78-05, 78-08, 78-09, 78-10 | Disposed/retired rule across KPI and cost view | SATISFIED | Truth 4 |
| COST-07 | 78-01, 78-06, 78-07, 78-08, 78-10, 78-11, 78-12, 78-13, 78-14, 78-15 | Explicit tenant on every route, no `$lookup`/cache, two-tenant isolation; UI follows the rule | SATISFIED | Truths 5 to 10 |

All five IDs appear in plan frontmatter and in REQUIREMENTS.md. No orphaned requirement (COST-04/05 are Phase 79, COST-08 Phase 80). REQUIREMENTS.md still shows COST-01/02/03/06/07 as "Gaps Found" from the earlier revert; flipping them back to Complete is the orchestrator's completion step and I did not edit it.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| all phase files touched this round | - | TBD/FIXME/XXX scan | none | clean |
| `backend/itam_reporting_endpoints.py` | 236 | IN-01 (still open, accepted in A-78-24): an Owner's fabricated `X-Tenant-ID` is accepted, so a save under a bogus header now writes one definition under a tenant id that does not exist, next to the export record IN-01 already described | Info | Owner tier only (T-78-32 accepted); no real tenant's data is exposed |
| review ledger | - | WR-03 and IN-01, IN-03, IN-06..IN-09 open per 78-REVIEW-DISPOSITION.md | Warning/Info | Documentation, contract and test-hygiene items; none falsifies a must-have |
| `components/itam/ReportsPanel.tsx` | 56-67 | A Support user who has a selected tenant gets the no-tenant state only after the first rejected request, because the client cannot know the server ignores the header | Info | By design (A-78-39); wording of the Select block reads slightly off for Support |

### Human Verification Required

#### 1. Live check on the deployed build

**Test:** After the user restarts the backend (78-12) and publishes the UI (78-13..15), open ITAM as a Platform Owner with a tenant selected and with none, and as Platform Support with none. As the Owner, run, preview, save, export and delete a custom report; switch tenant while a pre-built run and an export are in flight; run report A, then fail report B.
**Expected:** See the `human_verification` entry in the frontmatter.
**Why human:** Needs the deployed system and real sessions. The live backend still runs pre-78-12 code, so until the restart an Owner's custom report routes still behave as before; until the UI publish the old Reports tab is live. Deploy, publish and push are the user's actions.

### Gaps Summary

None. G-78-WR02, G-78-WR04, G-78-IN05 and G-78-IN04 are closed in committed HEAD and proven by passing behavioural tests, the earlier five ROADMAP truths and the 78-06 truth still hold, and all five requirement IDs are satisfied in code. The only open item is the user-owned post-deploy live check.

---

_Verified: 2026-11-17T09:00:00Z_
_Verifier: Claude (gsd-verifier)_
