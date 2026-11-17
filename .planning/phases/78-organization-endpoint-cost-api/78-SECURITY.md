---
phase: "78"
slug: "organization-endpoint-cost-api"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-11-17"
---

# Phase 78 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| client -> /api/itam/costs/* | Untrusted session or API-key caller, untrusted X-Tenant-ID header | Tenant asset cost figures (confidential, per tenant) |
| client -> /api/itam/costs/assets{,/{id}} | Untrusted asset id, paging and filter parameters | Per-asset cost rows |
| client -> /api/itam/kpis | Session or API key; Owner X-Tenant-ID header | Tenant KPI totals |
| client -> /api/itam/reports/prebuilt/{key}/run, /export | Session or API key with manage:assets; Owner X-Tenant-ID header | Report rows and export files |
| Owner selection -> X-Tenant-ID | Only the Owner's own switcher value is sent; the server decides whether to honour it | Tenant id |
| handler / itam_cost_service loaders -> TenantIsolatedDatabase | The wrapper skips scoping for a platform-admin ambient tenant, so every cost read carries an explicit tenantId | Tenant-scoped queries |
| KPI -> licences, warranty, overdue reads | These rely on the wrapper's ambient tenant, re-aligned by the resolver's set_tenant_id | Tenant KPI inputs |
| cost service -> agents collection | Another tenant's agent could name an asset id | Agent status joined onto assets |
| asset documents -> compute_asset_cost | Stored fields of any type (hand-entered, imported or legacy) | Purchase cost, dates, lifecycle status |
| cost surfaces -> each other | Divergent computations would show different money figures to the same tenant | Book value totals |
| export -> static/reports files + itam_report_exports | The export record's tenant decides who may download the file | Report files |
| server error text -> UI | Only the existing toast/plain-text paths render server strings | Error detail text |
| browser state -> rendered figure / report table | A stale response or result for a previous tenant must not render | KPI figures, report rows |
| test process -> MongoDB / backend/static/reports / working tree | Throwaway omni_test_* databases only; export files and the user's uncommitted work left as they were | Test data |
| async report response -> ReportsPanel state (78-11) | A response may arrive after the tenant selection or the active request changed; it must not become the rendered result | Report rows, title, export controls |
| executor -> user's working tree (78-11) | The user's uncommitted hunks sit in two files the gap plan edits and three it must not touch | Uncommitted user edits |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-78-01 | Information Disclosure | itam_cost_service loaders under a platform-admin ambient context | high | mitigate | `require_tenant` in `backend/itam_cost_service.py` refuses empty/platform-admin; explicit `{"tenantId": tenant_id}` on the assets, asset_models and agents finds (lines 151, 161, 179); refusal + platform-admin ambient real-Mongo tests in `test_itam_cost_service.py` (78-09) | closed |
| T-78-02 | Information Disclosure | Owner X-Tenant-ID choice reset by verify_token_async, then a blended read | high | mitigate | `backend/itam_tenant_scope.py:30-39` reads `X-Tenant-ID` itself and calls `tenant_context.set_tenant_id`; owner-with-header tests through the real TenantMiddleware in `test_itam_cost_isolation.py` (78-07, mutation-checked) | closed |
| T-78-03 | Elevation of Privilege | Non-owner sending X-Tenant-ID | high | mitigate | Override only when `auth_source == "session"` and `platform_tier(role) == "owner"` (`itam_tenant_scope.py:33-34`); tenant-admin spoof test ignored (78-07) | closed |
| T-78-04 | Elevation of Privilege | Narrow-scope API key reading cost data | medium | mitigate | Cost router mounted behind the ITAM API-key catalogue guard (`catalogue_mounts_assets.py`); `_require_itam_viewer` on every cost route (`itam_cost_endpoints.py`); real-app probes: view:assets key 403 (78-01) | closed |
| T-78-05 | Information Disclosure | Exception text in a 500 | low | mitigate | Generic "Internal server error" detail in `itam_cost_endpoints.py`; test asserts the exception text is absent (78-01) | closed |
| T-78-06 | Information Disclosure | ItamKpiPanel after a tenant switch | medium | mitigate | `cancelled` flag drops stale responses and data is cleared before each request in `components/itam/ItamKpiPanel.tsx`; stale-response tests (78-02) | closed |
| T-78-07 | Tampering (script injection) | Rendering the server's 400 detail | low | mitigate | Detail is only regex-matched; no `dangerouslySetInnerHTML` in `ItamKpiPanel.tsx` (0 occurrences) | closed |
| T-78-08 | Information Disclosure | GET /costs/assets/{id} (IDOR) | high | mitigate | Row taken from the tenant-scoped computation only; identical `{"detail": "Asset not found"}` 404 for unknown and foreign ids (`itam_cost_endpoints.py`); byte-identical test in 78-07 | closed |
| T-78-09 | Denial of Service | Whole-tenant recompute per page request | medium | mitigate | One projected read per collection (counted in `test_itam_cost_assets.py`); `page_size` capped at 100 (422 above); no cache | closed |
| T-78-10 | Information Disclosure | Agent join across tenants | high | mitigate | `load_agents_by_asset` queries `{"tenantId": tenant_id, "assetId": {"$in": ids}}` (`itam_cost_service.py:179`); joined only on `agents.assetId`, never hostname; tenant-b agent never appears (78-03) | closed |
| T-78-11 | Information Disclosure | /api/itam/kpis for a Super Admin (blended across tenants) | high | mitigate | `resolve_itam_tenant` first in `get_itam_kpis` (`itam_kpi_endpoints.py:43`), 400 "Select a tenant" for platform-admin/empty; route test (78-04) and isolation test (78-07) | closed |
| T-78-12 | Information Disclosure | Licence/warranty/overdue reads after an Owner header override | high | mitigate | Resolver's `set_tenant_id` re-aligns the wrapper; mutation run with it disabled failed `test_owner_header_scopes_every_kpi` (78-04) | closed |
| T-78-13 | Information Disclosure | Pre-built run/export for a Super Admin (blended across tenants) | high | mitigate | `resolve_itam_tenant` first in `run_prebuilt_report` and `export_prebuilt_report` (`itam_reporting_endpoints.py:70, 112`); 400 tests prove no database read; export spy records the resolved tenant (78-05) | closed |
| T-78-14 | Information Disclosure | Download of an export file | low | accept | Existing control unchanged (download route untouched by the phase diff `fd4e00f24..HEAD`): tenant ownership check on `itam_report_exports`, Super Admin bypass as before; exports now record the resolved tenant. See AR-78-02 | closed |
| T-78-15 | Information Disclosure | ReportsPanel after a tenant switch | medium | mitigate | Ref-guarded reset of result/activeKind/activeKey/page on `tenantId` change in `components/itam/ReportsPanel.tsx`; rerender tests for another tenant and for none (78-06). The 78-VERIFICATION.md gap (78-REVIEW WR-01: no stale-response guard, `running` not reset) was closed by gap plan 78-11, see T-78-27: `runSeq` guard on every async writer, `setRunning(false)` in the tenant-change effect, `resultIsCurrent` render gate, console test "a pre-built run for the previous tenant that resolves after the switch renders nothing" (`src/__tests__/ITAMConsole.test.tsx:379`) | closed |
| T-78-16 | Information Disclosure | Pre-built run without a tenant | low | mitigate | Run buttons disabled with `needsTenant` (`ReportsPanel.tsx`); server resolver 400s regardless (78-05) | closed |
| T-78-17 | Tampering | Isolation test touching live data or leaving files | medium | mitigate | `mongo_db` throwaway database in `test_itam_cost_isolation.py`; export files deleted in `finally` and an autouse fixture; `backend/static/reports` git status unchanged (78-07) | closed |
| T-78-18 | Information Disclosure | Tenant context leaking between concurrent requests | high | mitigate | `asyncio.gather` rounds (10 x 8 requests) through the real middleware assert exact per-tenant totals (78-07) | closed |
| T-78-19 | Repudiation / Tampering (integrity of reported figures) | KPI, report, summary and list drifting apart | medium | mitigate | Four-way parity plus per-asset book-value route parity under one fixed clock, `test_itam_cost_parity.py` (78-08) | closed |
| T-78-20 | Denial of Service | Full-tenant recompute on large tenants | medium | mitigate | Read-count and time bound at 20,000 assets, `test_itam_cost_scale.py`; measured 0.15-0.29 s against a 10 s bound (78-08) | closed |
| T-78-21 | Tampering | Tests leaving data in MongoDB | low | mitigate | `mongo_db` drops its database including the 20k seed; omni_test_* list empty before/after the phase command (78-10) and after the 2026-11-17 validation re-run (0 databases) | closed |
| T-78-22 | Tampering (integrity of reported figures) | compute_asset_cost drifting from compute_book_value (Phase 59 D-04) | medium | mitigate | 13-row golden table on both functions at the same `now` (`test_itam_cost_service.py`); `backend/itam_finance_service.py` unchanged (`git diff fd4e00f24..HEAD` empty) | closed |
| T-78-23 | Denial of Service | One malformed asset document failing a whole tenant's read | medium | mitigate | Malformed-input tests (string/float/negative/bool cost, bad life, bad dates, non-string lifecycleStatus); 78-09 fixed the list/dict `lifecycleStatus` crash and the mixed-type sort crash (7660a8cf0) | closed |
| T-78-24 | Information Disclosure | A loader called for the platform context, or a cache decorator, aggregation join or raw database handle added later | high | mitigate | ValueError refusal on all four entry points; real-Mongo test under a platform-admin ambient; static source scan of the three cost modules (`test_itam_cost_service.py`, 78-09) | closed |
| T-78-25 | Repudiation | A phase regression recorded as a pre-existing failure | medium | mitigate | The one full-suite failure (`test_patch_rollout_boot.py`) re-run on `fd4e00f24` and failed identically under the same collection delay (78-10-SUMMARY.md) | closed |
| T-78-26 | Tampering | The temporary pre-phase worktree left registered or created inside the repository | low | mitigate | Worktree in the session scratchpad, removed and pruned; `git worktree list` identical before and after (78-10) | closed |
| T-78-27 | Information Disclosure | ReportsPanel async writers (`runPrebuilt`, `runSavedCustom`, `handlePreviewCustom`) after a tenant switch or a newer request (78-11) | medium | mitigate | `runSeq` ref (`components/itam/ReportsPanel.tsx:88`) taken by every run and preview (`:107`, `:132`, `:158`) and bumped by the tenant-change effect (`:93`); superseded responses and failures dropped (`if (seq !== runSeq.current) return`); `running` cleared only by the current request; result block gated on `resultIsCurrent` (`:222`, `:321`); 7 tests in `src/__tests__/ITAMReportsPanelStaleResponse.test.tsx` plus the console test, RED recorded before each fix (0cebd4d9d, ebdca3fd7); full frontend suite 2,242 passed | closed |
| T-78-28 | Tampering | User's uncommitted hunks in ReportsPanel.tsx, ITAMConsole.test.tsx, App.tsx, services/apiService.ts, .planning/ui-reviews/.gitignore (78-11) | medium | mitigate | Patch reverse-apply staging with `git update-index`; after the last commit `git diff --cached --quiet` exits 0, `git diff --numstat` shows `0 1` for each user-removed lint comment, HEAD still holds both comments, and the other three files remain ` M` and unstaged (orchestrator check 2026-11-17) | closed |
| T-78-29 | Information Disclosure | Custom report run, preview and export for a platform session (rows and Book Value blended across tenants) | high | mitigate | `resolve_itam_tenant(request, current_user)` is the first call in `run_saved_custom_report`, `preview_custom_report` and `export_custom_report` (`backend/itam_reporting_endpoints.py:280, 327, 355`; export resolves before the format check); Owner without a tenant 400, Owner with a tenant sees only that tenant's rows and Book Value, through the real middleware and real Mongo in `test_itam_custom_report_tenant.py` (78-12, 21 tests) | closed |
| T-78-30 | Information Disclosure / Tampering | Saved-definition list, get, save and delete for a platform session | medium | mitigate | Resolver first in `create_custom_report`, `list_custom_reports`, `get_custom_report`, `delete_custom_report` (`itam_reporting_endpoints.py:236, 261, 294, 308`); every `itam_reports` find/find_one/delete_one/insert carries `"tenantId": tenant_id` (lines 241, 263, 296, 310, 329, 362); foreign and unknown ids answer the same 404 and a refused delete leaves the document (78-12) | closed |
| T-78-31 | Elevation of Privilege | X-Tenant-ID sent by a tenant admin, Platform Support or Billing on custom routes | high | mitigate | Header honoured only when `auth_source == "session"` and `platform_tier(role) == "owner"` (`itam_tenant_scope.py:30-34`, resolver code unchanged by 78-12); tests: tenant admin spoof ignored, Support 400 on list/get and 403 elsewhere, Billing 403 on all seven, 10 concurrent rounds never mix (78-12) | closed |
| T-78-32 | Tampering | Owner saving a custom definition under a fabricated X-Tenant-ID | low | accept | See AR-78-03 | closed |
| T-78-33 | Tampering | ReportsPanel export and pagination after a failed or superseded run (WR-04) | medium | mitigate | One `shown` value (kind, key, page, data) plus a separate `pending` run in `components/itam/ReportsPanel.tsx:46-47`, written only after the runSeq check; title, export target and page controls derived from it in `components/itam/ReportResultView.tsx`; tests T-h..T-k in `ITAMReportsPanelStaleResponse.test.tsx` (78-13) | closed |
| T-78-34 | Information Disclosure | Export started for the previous tenant downloading after an Owner tenant switch (IN-05) | low | mitigate | `tenantEpoch` ref bumped by the tenant-change effect (`ReportsPanel.tsx:107-113`); `handleExport` skips download and toast for a stale epoch and resets `exportingFormat` only for the current one (lines 222-233); tests T-l..T-n (78-13) | closed |
| T-78-35 | Tampering | The user's uncommitted hunk in ReportsPanel.tsx and other user-modified files during 78-13 | medium | mitigate | Insertion staging with `git update-index --cacheinfo`; after the gap round the user numstat is unchanged (App.tsx 21/15, ReportsPanel.tsx 0/1, apiService.ts 10/0, ITAMConsole.test.tsx 0/1, ITAMReportsPanel.test.tsx 4/3) and the index is clean | closed |
| T-78-36 | Information Disclosure | Saved-reports list after a tenant switch and custom calls sent without the selected tenant | medium | mitigate | Trailing `tenantId` on `listItamCustomReports`, `saveItamCustomReport`, `deleteItamCustomReport`, `previewItamCustomReport`, `runItamCustomReport` and `generateItamReport` (`services/apiService.ts:5992-6099`); `listSeq` guard and list cleared on a switch (`ReportsPanel.tsx:75-89`); no list request without a tenant; `ITAMReportsPanelTenantRule.test.tsx` (78-14) | closed |
| T-78-37 | Tampering | A save or delete completing after a tenant switch | low | mitigate | `tenantEpoch` captured in the save and delete handlers; stale completions return before reload, toast or state change (`ReportsPanel.tsx:187-212`); tests for both (78-14) | closed |
| T-78-38 | Tampering | User hunks in services/apiService.ts, ReportsPanel.tsx, ITAMConsole.test.tsx, ITAMReportsPanel.test.tsx during 78-14 | medium | mitigate | Insertion and patch staging with `git update-index`; HEAD lacks `setUserPassword` and the `ComponentProps` import, both removed lint lines stay in HEAD; numstat unchanged (see T-78-35) | closed |
| T-78-39 | Information Disclosure | Reports tab for Platform Support (enabled controls, server detail shown in toasts) | low | mitigate | `needsTenant = (isSuperAdminView \|\| isPlatformView) && !tenantId` (`components/itam/ITAMConsole.tsx:85`), App.tsx passes `isPlatformView={isPlatformRoleName(...)}`; `takeTenantRejection` matches the 400 detail with `SELECT_TENANT_RE` and shows the no-tenant state in the list, pre-built run, saved run and export catches (`ReportsPanel.tsx:59-64, 90, 132, 154, 230`) (78-15) | closed |
| T-78-40 | Elevation of Privilege | Client-side gating read as access control | low | accept | See AR-78-04 | closed |
| T-78-41 | Tampering | User hunks in App.tsx, ReportsPanel.tsx, ITAMConsole.test.tsx during 78-15 | medium | mitigate | Patch and insertion staging with `git update-index`; HEAD App.tsx lacks `handleSetUserPassword` while the working tree keeps it; services/apiService.ts and ITAMReportsPanel.test.tsx untouched; numstat unchanged (see T-78-35) | closed |
| T-78-SC | Tampering | npm/pip installs | low | accept | No package installed: `package.json`, lock files and requirements files unchanged over `fd4e00f24..HEAD`, including gap plan 78-11 (`edbb1bb46..HEAD` dependency-file diff empty) and gap round 2 78-12..78-15 (`fd4e00f24..HEAD` dependency-file diff still empty). See AR-78-01 | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-78-01 | T-78-SC | No npm or pip package is added by any Phase 78 plan; verified by an empty dependency-file diff over `fd4e00f24..HEAD` | Plan-time disposition (78 plans, bd9d608f9 / eb208bf1b) | 2026-11-17 |
| AR-78-02 | T-78-14 | The export download route is unchanged; its existing tenant-ownership check on `itam_report_exports` (Super Admin bypass as before) stays the control, and exports now record the resolved tenant | Plan-time disposition (78-05 plan, eb208bf1b) | 2026-11-17 |
| AR-78-03 | T-78-32 | Only the Owner tier can choose X-Tenant-ID; a fabricated id stores a definition under a tenant that does not exist and reads or exposes no real tenant's data. Same class as 78-REVIEW IN-01 (unvalidated Owner X-Tenant-ID), which stays out of scope (A-78-24) | Plan-time disposition (78-12 plan, a96451eb8) | 2026-11-17 |
| AR-78-04 | T-78-40 | The client no-tenant state is presentation only; the resolver's 400 (T-78-29..T-78-31) and the view and route guards' 403 remain the controls and were not changed by 78-15 (PROH-78-16) | Plan-time disposition (78-15 plan, 05bbe5d7b) | 2026-11-17 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-11-17 | 27 | 27 | 0 | secure-phase (orchestrator, L1 grep depth; plan-time register, auditor skipped per short-circuit rule) |
| 2026-11-17 | 27 | 26 | 0 (1 open below the high threshold: T-78-15) | orchestrator, after gsd-verifier found the ReportsPanel stale-response gap; also noted: 78-REVIEW WR-02 (custom report routes keep today's tenant handling per A-78-17, so a Platform Owner's custom report can blend tenants) has no accepted-risk row yet and awaits the user's call |
| 2026-11-17 | 29 | 29 | 0 | secure-phase after gap plan 78-11 (orchestrator, L1 grep depth; plan-time register, auditor skipped per short-circuit rule): T-78-27 and T-78-28 added and closed, T-78-15 closed again; WR-02 still awaits the user's call |
| 2026-11-17 | 42 | 42 | 0 | secure-phase after gap round 2 78-12..78-15 (orchestrator, L1 grep depth; plan-time register, auditor skipped per short-circuit rule): T-78-29..T-78-41 added and closed (T-78-32 and T-78-40 accepted as AR-78-03/AR-78-04); WR-02 resolved by the user's decision to fix it (D-13 amended), now mitigated by T-78-29..T-78-31 |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-11-17 (threats_open 0 at the high threshold; T-78-15, medium, reopened the same day after verification and closed again after gap plan 78-11 added T-78-27/T-78-28; all 29 threats closed. 78-REVIEW WR-02, custom report routes keeping today's tenant handling, still has no accepted-risk row and awaits the user's call). Re-verified 2026-11-17 after gap round 2 (78-12..78-15): 42 threats, all closed, threats_open 0; the user chose to fix WR-02 (D-13 amended), and the custom report routes now resolve one tenant (T-78-29..T-78-31)

## Security Audit 2026-11-17

| Metric | Count |
|---|---|
| Threats found | 29 |
| Closed | 29 |
| Open | 0 |

## Security Audit 2026-11-17

| Metric | Count |
|---|---|
| Threats found | 42 |
| Closed | 42 |
| Open | 0 |
