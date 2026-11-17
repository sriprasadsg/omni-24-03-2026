---
phase: "78"
slug: "organization-endpoint-cost-api"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-11-16"
---

# Phase 78 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 + pytest-asyncio (auto mode); Vitest 5.0.0 |
| **Config file** | repo-root `pytest.ini` (asyncio_mode = auto); Vitest via package scripts |
| **Quick run command** | `backend/venv/bin/python -m pytest backend/tests/test_itam_cost_endpoints.py -q -p no:cacheprovider` in waves 1-2; from wave 3 (after 78-09 creates it) add `backend/tests/test_itam_cost_service.py` |
| **Full suite command** | `backend/venv/bin/python -m pytest backend/tests/test_itam_custom_report_tenant.py backend/tests/test_itam_cost_service.py backend/tests/test_itam_cost_endpoints.py backend/tests/test_itam_cost_assets.py backend/tests/test_itam_kpi_cost_rules.py backend/tests/test_itam_report_cost_rules.py backend/tests/test_itam_cost_parity.py backend/tests/test_itam_cost_isolation.py backend/tests/test_itam_cost_scale.py backend/tests/test_itam_reporting_kpis.py backend/tests/test_itam_reporting_prebuilt.py backend/tests/test_itam_reporting_builder.py backend/tests/test_itam_reporting_export.py backend/tests/test_itam_finance_bookvalue.py backend/tests/test_catalogue_slice_assets.py -q -p no:cacheprovider -rs` (0 skipped required) |
| **Frontend command** | `npx vitest run src/__tests__/ITAMKpiPanel.test.tsx src/__tests__/ITAMConsole.test.tsx src/__tests__/ITAMReportsPanel.test.tsx src/__tests__/ITAMReportsPanelStaleResponse.test.tsx src/__tests__/ITAMReportsPanelTenantRule.test.tsx` and `npm run build` |
| **Estimated runtime** | ~60 seconds (baseline: the 3 edited suites run 55 tests in 2.1 s; the 20k-asset scale test dominates) |

All commands run from the repo root. Real-Mongo tests use `tests/_mongo_test_db.mongo_db` against the local mongod (8.0.34, `127.0.0.1:27017`); a skipped isolation or parity test is **not** an acceptable gate.

---

## Sampling Rate

- **After every task commit:** Run the quick command, plus the touched file's own existing suite when a refactor edits the KPI, prebuilt report or custom builder
- **After every plan wave:** Run the full suite command; add the frontend command once the tile wave lands
- **Before `/gsd-verify-work`:** Full suite + `npm run build` + `npx vitest run src/__tests__` green, and the isolation and parity tests confirmed as run (not skipped)
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

Seeded per requirement from RESEARCH.md; the planner binds task IDs.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 78-01-T1 | 78-01 | 1 | COST-01 | T-78-01, T-78-02, T-78-03 | One shared computation through the summary route; tracer expectation computed with `compute_book_value`; resolver matrix | route + real-Mongo | `backend/venv/bin/python -m pytest backend/tests/test_itam_cost_endpoints.py -q -p no:cacheprovider -rs` | ✅ | ✅ green |
| 78-01-T1 | 78-01 | 1 | COST-02 | T-78-05 | Unpriced is `null`, never 0; generic 500 | route | `backend/venv/bin/python -m pytest backend/tests/test_itam_cost_endpoints.py -q -p no:cacheprovider -rs` | ✅ | ✅ green |
| 78-01-T2 | 78-01 | 1 | COST-07 (D-16, D-15 amended 2026-11-16) | T-78-04 | 403 without `view:itam` (Billing included); API-key scope narrowing | real-app probe | `backend/venv/bin/python -m pytest backend/tests/test_catalogue_slice_assets.py -q -p no:cacheprovider` | ✅ | ✅ green |
| 78-09-T1 | 78-09 | 3 | COST-01, COST-06 | T-78-22 | Golden table on both functions; one-reason invariant; disposed/retired rule | unit | `backend/venv/bin/python -m pytest backend/tests/test_itam_cost_service.py backend/tests/test_itam_finance_bookvalue.py -q -p no:cacheprovider -rs` | ✅ | ✅ green |
| 78-09-T2 | 78-09 | 3 | COST-02, COST-07 | T-78-23, T-78-24 (verifies T-78-01) | Garbage input never raises or floats; every loader refuses `platform-admin`; explicit tenant filter under a `platform-admin` ambient; static scan | unit + real-Mongo | `backend/venv/bin/python -m pytest backend/tests/test_itam_cost_service.py backend/tests/test_itam_cost_endpoints.py backend/tests/test_itam_cost_assets.py backend/tests/test_itam_finance_bookvalue.py -q -p no:cacheprovider -rs` | ✅ | ✅ green |
| 78-03-T1, T2 | 78-03 | 2 | COST-03 | T-78-08, T-78-10 | Detail route 404s an asset id outside the tenant; agent join tenant-scoped | route + real-Mongo | `backend/venv/bin/python -m pytest backend/tests/test_itam_cost_assets.py -q -p no:cacheprovider -rs` | ✅ | ✅ green |
| 78-04-T1, T2 | 78-04 | 2 | COST-06 (KPI), COST-07 | T-78-11, T-78-12 | KPI drops disposed/retired from value, keeps pie; 400 for platform-admin | unit + real-Mongo | `backend/venv/bin/python -m pytest backend/tests/test_itam_kpi_cost_rules.py backend/tests/test_itam_reporting_kpis.py -q -p no:cacheprovider -rs` | ✅ | ✅ green |
| 78-05-T1, T2 | 78-05 | 2 | COST-06 (report), COST-07 | T-78-13 | Report drops disposed/retired; run/export 400 for platform-admin | unit + route | `backend/venv/bin/python -m pytest backend/tests/test_itam_report_cost_rules.py backend/tests/test_itam_reporting_prebuilt.py backend/tests/test_itam_reporting_builder.py -q -p no:cacheprovider -rs` | ✅ | ✅ green |
| 78-02-T1, T2 | 78-02 | 1 | D-14 tile (COST-02, COST-07) | T-78-06 | No stale tenant figure; Not tracked, never $0 | vitest | `npx vitest run src/__tests__/ITAMKpiPanel.test.tsx` | ✅ | ✅ green |
| 78-06-T1, T2 | 78-06 | 2 | D-14 console + Reports (COST-07) | T-78-15, T-78-16 | Tenant threaded; reports reset on switch | vitest + build | `npx vitest run src/__tests__` and `npm run build` | ✅ | ✅ green |
| 78-07-T1, T2 | 78-07 | 3 | COST-07 | T-78-02, T-78-03, T-78-18 | Tenant A never sees B; Owner header via real middleware; per amended D-15 (2026-11-16): Support 400 on cost/KPI and 403 on pre-built report run/export, Billing 403 everywhere | real-Mongo + real middleware | `backend/venv/bin/python -m pytest backend/tests/test_itam_cost_isolation.py -q -p no:cacheprovider -rs` | ✅ | ✅ green |
| 78-08-T1 | 78-08 | 4 | COST-01, COST-06 (parity) | T-78-19 | KPI = report = summary = list | real-Mongo | `backend/venv/bin/python -m pytest backend/tests/test_itam_cost_parity.py -q -p no:cacheprovider -rs` | ✅ | ✅ green |
| 78-08-T2 | 78-08 | 4 | Scale (COST-07 perf) | T-78-20, T-78-21 | Bounded reads, no N+1 | real-Mongo | `backend/venv/bin/python -m pytest backend/tests/test_itam_cost_scale.py -q -p no:cacheprovider -rs` | ✅ | ✅ green |
| 78-10-T1 | 78-10 | 5 | COST-01, COST-02, COST-03, COST-06, COST-07 | T-78-21 (check) | Phase command 0 failed / 0 skipped; no leftover `omni_test_*` database or report file (PROH-78-05) | real-Mongo | the **Full suite command** above, with before/after listings | ✅ | ✅ green (310 passed, 0 skipped, re-run 2026-11-17) |
| 78-10-T2 | 78-10 | 5 | COST-01, COST-02, COST-03, COST-06, COST-07 | T-78-25, T-78-26 | No phase regression; every failure checked on the commit before 78-01 | full backend suite | `TICKET_ATTACHMENT_DIR=$(mktemp -d) FILE_SHARE_DIR=$(mktemp -d) backend/venv/bin/python -m pytest backend/tests -q -p no:cacheprovider` | ✅ | ✅ green (no phase regression; the 1 failure, test_patch_rollout_boot, is clock-dependent and fails identically on fd4e00f24, see 78-10-SUMMARY.md) |
| 78-11-T1 | 78-11 (gap) | 3 | COST-07 (D-14 amended, UI-SPEC R3) | T-78-27 (completes T-78-15) | A pre-built run for tenant A that resolves after the switch to tenant B renders no title, rows or export buttons; a later run for B renders | vitest (console level) | `npx vitest run src/__tests__/ITAMConsole.test.tsx src/__tests__/ITAMReportsPanel.test.tsx` | ✅ | ✅ green (RED recorded first: failed on the stale "Laptop 1" row before b26ea046e) |
| 78-11-T2 | 78-11 (gap) | 3 | COST-07 | T-78-27, T-78-28 | Saved custom run and builder preview drop stale responses; out-of-order runs keep the latest; superseded failure raises no toast; same-tenant rerender keeps the result; user WIP stays unstaged | vitest + build | `npx vitest run src/__tests__/ITAMReportsPanelStaleResponse.test.tsx src/__tests__/ITAMReportsPanel.test.tsx src/__tests__/ITAMConsole.test.tsx`, `npx vitest run src/__tests__`, `npm run build` | ✅ | ✅ green (62 passed; full suite 2,242 passed; build exit 0; RED recorded first for the custom-run and preview tests) |
| 78-12-T1 | 78-12 (gap) | 1 | COST-07, COST-01 (D-13 amended 2026-11-17) | T-78-29 | A saved custom run covers exactly the resolved tenant through token -> TenantMiddleware -> guard -> resolve_itam_tenant -> real MongoDB; Owner without a tenant gets 400 | real-Mongo + real middleware | `backend/venv/bin/python -m pytest backend/tests/test_itam_custom_report_tenant.py -q -p no:cacheprovider -rs` | ✅ | ✅ green (RED recorded first: 200 == 400 and rowCount 4 == 2) |
| 78-12-T2 | 78-12 (gap) | 1 | COST-07, COST-01 | T-78-29, T-78-30, T-78-31 | All seven custom routes (save, list, preview, get, delete, run, export) resolve one tenant; foreign and unknown ids answer the same 404; tenant admin header ignored; Support 400/403 and Billing 403; 10 concurrent rounds never blend; custom Book Value equals `bookValueCents` | real-Mongo + real middleware | `backend/venv/bin/python -m pytest backend/tests/test_itam_custom_report_tenant.py -q -p no:cacheprovider -rs` and the **Full suite command** | ✅ | ✅ green (21 passed; phase command + module 331 passed, 0 skipped, re-run 2026-11-17 by validate-phase with no leftover report file or `omni_test_*` database) |
| 78-13-T1 | 78-13 (gap) | 1 | COST-07 (D-14 amended) | T-78-33 | A failed run after a successful one keeps the earlier report's title, rows and export target (one `shown` value) | vitest | `npx vitest run src/__tests__/ITAMReportsPanelStaleResponse.test.tsx src/__tests__/ITAMReportsPanel.test.tsx src/__tests__/ITAMConsole.test.tsx` | ✅ | ✅ green (RED recorded first: export argument `warranty_expiring` instead of `asset_value`) |
| 78-13-T2 | 78-13 (gap) | 1 | COST-07 | T-78-33, T-78-34, T-78-35 | Preview supersede, pagination and the in-flight state follow the shown report; an export started before a tenant switch neither downloads nor toasts; user WIP stays unstaged | vitest + build | `npx vitest run src/__tests__/ITAMReportsPanelStaleResponse.test.tsx`, `npx vitest run src/__tests__`, `npm run build` | ✅ | ✅ green (RED recorded first for T-l and T-m) |
| 78-14-T1 | 78-14 (gap) | 2 | COST-07 (D-13, D-14 amended) | T-78-36 | A saved custom report's run, export and delete carry the Owner's selected tenant | vitest | `npx vitest run src/__tests__/ITAMReportsPanelStaleResponse.test.tsx src/__tests__/ITAMReportsPanel.test.tsx src/__tests__/ITAMConsole.test.tsx` | ✅ | ✅ green (RED recorded first) |
| 78-14-T2 | 78-14 (gap) | 2 | COST-07 | T-78-36, T-78-37 | List, save and preview carry the tenant; the saved list clears on a switch and drops late responses (listSeq); a save or delete finishing after a switch has no side effect | vitest | `npx vitest run src/__tests__/ITAMReportsPanelTenantRule.test.tsx` | ✅ | ✅ green (RED recorded first: 10 of 17 failed) |
| 78-14-T3 | 78-14 (gap) | 2 | COST-07 | T-78-36, T-78-38 | No tenant: no list request, Create Custom Report disabled with a note, builder hidden; user WIP stays unstaged | vitest + build | `npx vitest run src/__tests__/ITAMReportsPanelTenantRule.test.tsx src/__tests__/ITAMKpiPanel.test.tsx`, `npx vitest run src/__tests__`, `npm run build` | ✅ | ✅ green (RED recorded first on the missing copy key) |
| 78-15-T1 | 78-15 (gap) | 3 | COST-07 (D-14 amended, IN-04) | T-78-39, T-78-40 | Every platform tier without a tenant (Support as well as the Owner) gets the Select-a-tenant state on the tile and the Reports tab, with no request and no toast; Billing refused by the view gate | vitest | `npx vitest run src/__tests__/ITAMConsole.test.tsx src/__tests__/ITAMReportsPanelTenantRule.test.tsx src/__tests__/ITAMKpiPanel.test.tsx` | ✅ | ✅ green (RED recorded first on the Support heading) |
| 78-15-T2 | 78-15 (gap) | 3 | COST-07 | T-78-39, T-78-41 | A "Select a tenant" rejection on the saved list, pre-built run, saved run or export shows the no-tenant state, not a toast; other errors still toast; user WIP stays unstaged | vitest + build | `npx vitest run src/__tests__/ITAMReportsPanelTenantRule.test.tsx`, `npx vitest run src/__tests__`, `npm run build` | ✅ | ✅ green (full suite 2,278 passed in 136 files; build exit 0; RED recorded first) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `backend/tests/test_itam_cost_service.py` — golden table, reason precedence invariant, type guards, disposed/retired rule, sort order, `platform-admin` argument refused on every loader, static no-`$lookup`/`cached` scan (78-09, wave 3, against the module as 78-03 leaves it; duplicates and placeholder serials are covered in `test_itam_cost_assets.py` by 78-03)
- [x] `backend/tests/test_itam_cost_endpoints.py` — summary route + resolver matrix, real-Mongo tracer (78-01)
- [x] `backend/tests/test_itam_cost_assets.py` — list/detail routes, agent join, duplicates, pagination, filters, 404 (78-03)
- [x] `backend/tests/test_itam_kpi_cost_rules.py`, `backend/tests/test_itam_report_cost_rules.py` — KPI and report rule tests in new files so the existing suites stay under 500 lines (78-04, 78-05)
- [x] `backend/tests/test_itam_cost_parity.py` — KPI vs report (parsed with `Decimal`) vs summary over one seeded tenant, plus `compute_asset_cost` vs `GET /api/assets/{id}/book-value` per asset, under one patched `utc_now`
- [x] `backend/tests/test_itam_cost_isolation.py` — real Mongo + real `TenantMiddleware` + real `TenantIsolatedDatabase`; Owner with/without `X-Tenant-ID`, Support 400, Billing 403, two tenants on every cost, KPI and report route
- [x] `backend/tests/test_itam_cost_scale.py` — ~20k assets via `insert_many`, `find`-call count bound, soft time bound
- [x] Extend `backend/tests/test_catalogue_slice_assets.py` — `/api/itam/costs/*` probes and API-key scope narrowing
- [x] Update `backend/tests/test_itam_reporting_kpis.py` (0 → null; no-tenant 403 → 400) and `backend/tests/test_itam_reporting_prebuilt.py`
- Framework install: none

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Super Admin tile on the live UI shows the selected tenant's figures, "Not tracked" and "Select a tenant" states | D-14 / COST-07 | Live deploy (backend restart, UI publish) is the user's action | After deploy: sign in as Platform Owner, open ITAM with no tenant selected (expect "Select a tenant"), then pick a tenant and compare the tile with `GET /api/itam/costs/summary` for that tenant |
| Custom reports section in the live UI follows the selected tenant and shows the no-tenant note (look of the disabled Create Custom Report button and the note wording, A-78-35) | D-13 / D-14 / COST-07 (78-14, 78-15) | Visual judgment on the deployed UI; behaviour is automated | After deploy: as Platform Owner with no tenant, open ITAM > Reports (expect the note and a disabled Create Custom Report); pick tenant A, save a custom report, switch to tenant B (A's definition must not appear) |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 60s (per-task quick commands; the full phase command takes 82 s)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated 2026-11-17 (validate-phase audit: 0 gaps; phase command 310 passed / 0 skipped; frontend 50 passed). Re-audited 2026-11-17 after gap plan 78-11: 0 gaps; 78-11 tasks green (62 passed across the three ReportsPanel/console suites; full frontend suite 2,242 passed; build exit 0). Re-audited 2026-11-17 after gap round 2 (78-12..78-15): 0 gaps; phase command + `test_itam_custom_report_tenant.py` 331 passed / 0 skipped; full frontend suite 2,278 passed in 136 files; build exit 0

## Validation Audit 2026-11-17

| Metric | Count |
|---|---|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |
