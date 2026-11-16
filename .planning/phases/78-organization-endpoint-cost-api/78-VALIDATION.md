---
phase: "78"
slug: "organization-endpoint-cost-api"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
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
| **Quick run command** | `backend/venv/bin/python -m pytest backend/tests/test_itam_cost_service.py backend/tests/test_itam_cost_endpoints.py -q -p no:cacheprovider` |
| **Full suite command** | `backend/venv/bin/python -m pytest backend/tests/test_itam_cost_service.py backend/tests/test_itam_cost_endpoints.py backend/tests/test_itam_cost_assets.py backend/tests/test_itam_kpi_cost_rules.py backend/tests/test_itam_report_cost_rules.py backend/tests/test_itam_cost_parity.py backend/tests/test_itam_cost_isolation.py backend/tests/test_itam_cost_scale.py backend/tests/test_itam_reporting_kpis.py backend/tests/test_itam_reporting_prebuilt.py backend/tests/test_itam_reporting_builder.py backend/tests/test_itam_reporting_export.py backend/tests/test_itam_finance_bookvalue.py backend/tests/test_catalogue_slice_assets.py -q -p no:cacheprovider -rs` (0 skipped required) |
| **Frontend command** | `npx vitest run src/__tests__/ITAMKpiPanel.test.tsx src/__tests__/ITAMConsole.test.tsx` and `npm run build` |
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
| 78-01-T1, T3 | 78-01 | 1 | COST-01 | T-78-01 | Golden table, one shared computation | unit + real-Mongo | `backend/venv/bin/python -m pytest backend/tests/test_itam_cost_service.py backend/tests/test_itam_cost_endpoints.py -q -p no:cacheprovider -rs` | ❌ W0 (created by the task) | ⬜ pending |
| 78-01-T1, T3 | 78-01 | 1 | COST-02 | T-78-05 | Unpriced/garbage input is `null`, never 0, never a 500 | unit + route | `backend/venv/bin/python -m pytest backend/tests/test_itam_cost_service.py backend/tests/test_itam_cost_endpoints.py -q -p no:cacheprovider -rs` | ❌ W0 (created by the task) | ⬜ pending |
| 78-01-T2 | 78-01 | 1 | COST-07 (D-16) | T-78-04 | 403 without `view:itam`; API-key scope narrowing | real-app probe | `backend/venv/bin/python -m pytest backend/tests/test_catalogue_slice_assets.py -q -p no:cacheprovider` | ✅ (extend) | ⬜ pending |
| 78-03-T1, T2 | 78-03 | 2 | COST-03 | T-78-08, T-78-10 | Detail route 404s an asset id outside the tenant; agent join tenant-scoped | route + real-Mongo | `backend/venv/bin/python -m pytest backend/tests/test_itam_cost_assets.py -q -p no:cacheprovider -rs` | ❌ W0 (created by the task) | ⬜ pending |
| 78-04-T1, T2 | 78-04 | 2 | COST-06 (KPI), COST-07 | T-78-11, T-78-12 | KPI drops disposed/retired from value, keeps pie; 400 for platform-admin | unit + real-Mongo | `backend/venv/bin/python -m pytest backend/tests/test_itam_kpi_cost_rules.py backend/tests/test_itam_reporting_kpis.py -q -p no:cacheprovider -rs` | partial | ⬜ pending |
| 78-05-T1, T2 | 78-05 | 2 | COST-06 (report), COST-07 | T-78-13 | Report drops disposed/retired; run/export 400 for platform-admin | unit + route | `backend/venv/bin/python -m pytest backend/tests/test_itam_report_cost_rules.py backend/tests/test_itam_reporting_prebuilt.py backend/tests/test_itam_reporting_builder.py -q -p no:cacheprovider -rs` | partial | ⬜ pending |
| 78-02-T1, T2 | 78-02 | 1 | D-14 tile (COST-02, COST-07) | T-78-06 | No stale tenant figure; Not tracked, never $0 | vitest | `npx vitest run src/__tests__/ITAMKpiPanel.test.tsx` | ✅ (extend) | ⬜ pending |
| 78-06-T1, T2 | 78-06 | 2 | D-14 console + Reports (COST-07) | T-78-15, T-78-16 | Tenant threaded; reports reset on switch | vitest + build | `npx vitest run src/__tests__` and `npm run build` | ✅ (extend) | ⬜ pending |
| 78-07-T1, T2 | 78-07 | 3 | COST-07 | T-78-02, T-78-03, T-78-18 | Tenant A never sees B; Owner header via real middleware; Support 400 / Billing 403 | real-Mongo + real middleware | `backend/venv/bin/python -m pytest backend/tests/test_itam_cost_isolation.py -q -p no:cacheprovider -rs` | ❌ W0 (created by the task) | ⬜ pending |
| 78-08-T1 | 78-08 | 3 | COST-01, COST-06 (parity) | T-78-19 | KPI = report = summary = list | real-Mongo | `backend/venv/bin/python -m pytest backend/tests/test_itam_cost_parity.py -q -p no:cacheprovider -rs` | ❌ W0 (created by the task) | ⬜ pending |
| 78-08-T2 | 78-08 | 3 | Scale (COST-07 perf) | T-78-20 | Bounded reads, no N+1 | real-Mongo | `backend/venv/bin/python -m pytest backend/tests/test_itam_cost_scale.py -q -p no:cacheprovider -rs` | ❌ W0 (created by the task) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_itam_cost_service.py` — golden table, reason precedence invariant, type guards, disposed/retired rule, duplicates, placeholder serials, sort order, `platform-admin` argument refused, static no-`$lookup`/`cached` scan
- [ ] `backend/tests/test_itam_cost_endpoints.py` — summary route + resolver matrix, real-Mongo tracer (78-01)
- [ ] `backend/tests/test_itam_cost_assets.py` — list/detail routes, agent join, duplicates, pagination, filters, 404 (78-03)
- [ ] `backend/tests/test_itam_kpi_cost_rules.py`, `backend/tests/test_itam_report_cost_rules.py` — KPI and report rule tests in new files so the existing suites stay under 500 lines (78-04, 78-05)
- [ ] `backend/tests/test_itam_cost_parity.py` — KPI vs report (parsed with `Decimal`) vs summary over one seeded tenant, plus `compute_asset_cost` vs `GET /api/assets/{id}/book-value` per asset, under one patched `utc_now`
- [ ] `backend/tests/test_itam_cost_isolation.py` — real Mongo + real `TenantMiddleware` + real `TenantIsolatedDatabase`; Owner with/without `X-Tenant-ID`, Support 400, Billing 403, two tenants on every cost, KPI and report route
- [ ] `backend/tests/test_itam_cost_scale.py` — ~20k assets via `insert_many`, `find`-call count bound, soft time bound
- [ ] Extend `backend/tests/test_catalogue_slice_assets.py` — `/api/itam/costs/*` probes and API-key scope narrowing
- [ ] Update `backend/tests/test_itam_reporting_kpis.py` (0 → null; no-tenant 403 → 400) and `backend/tests/test_itam_reporting_prebuilt.py`
- Framework install: none

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Super Admin tile on the live UI shows the selected tenant's figures, "Not tracked" and "Select a tenant" states | D-14 / COST-07 | Live deploy (backend restart, UI publish) is the user's action | After deploy: sign in as Platform Owner, open ITAM with no tenant selected (expect "Select a tenant"), then pick a tenant and compare the tile with `GET /api/itam/costs/summary` for that tenant |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
