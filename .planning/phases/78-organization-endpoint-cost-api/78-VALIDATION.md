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
| **Full suite command** | `backend/venv/bin/python -m pytest backend/tests/test_itam_cost_service.py backend/tests/test_itam_cost_endpoints.py backend/tests/test_itam_cost_parity.py backend/tests/test_itam_cost_isolation.py backend/tests/test_itam_cost_scale.py backend/tests/test_itam_reporting_kpis.py backend/tests/test_itam_reporting_prebuilt.py backend/tests/test_itam_reporting_builder.py backend/tests/test_itam_finance_bookvalue.py backend/tests/test_catalogue_slice_assets.py -q -p no:cacheprovider` |
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
| TBD | TBD | TBD | COST-01 | — | N/A | unit + real-Mongo | `backend/venv/bin/python -m pytest backend/tests/test_itam_cost_service.py backend/tests/test_itam_cost_parity.py -q -p no:cacheprovider` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | COST-02 | — | Unpriced/garbage input is `null`, never 0, never a 500 | unit + route | `backend/venv/bin/python -m pytest backend/tests/test_itam_cost_service.py backend/tests/test_itam_cost_endpoints.py -q -p no:cacheprovider` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | COST-03 | T-78 (foreign id) | Detail route 404s an asset id outside the tenant | route + real-Mongo | `backend/venv/bin/python -m pytest backend/tests/test_itam_cost_endpoints.py backend/tests/test_itam_cost_isolation.py -q -p no:cacheprovider` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | COST-06 | — | N/A | unit + parity | `backend/venv/bin/python -m pytest backend/tests/test_itam_cost_service.py backend/tests/test_itam_cost_parity.py backend/tests/test_itam_reporting_kpis.py backend/tests/test_itam_reporting_prebuilt.py -q -p no:cacheprovider` | partial | ⬜ pending |
| TBD | TBD | TBD | COST-07 | T-78 (tenant leak, guard drift, API-key scope) | 403 without `view:itam`; 400 for `platform-admin`/empty context; tenant A never sees B | route + real-Mongo + static | `backend/venv/bin/python -m pytest backend/tests/test_itam_cost_isolation.py backend/tests/test_catalogue_slice_assets.py -q -p no:cacheprovider` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | Scale (COST-07 perf) | — | Bounded reads, no N+1 | real-Mongo | `backend/venv/bin/python -m pytest backend/tests/test_itam_cost_scale.py -q -p no:cacheprovider` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | D-14 tile | — | N/A | vitest | `npx vitest run src/__tests__/ITAMKpiPanel.test.tsx src/__tests__/ITAMConsole.test.tsx` | ✅ (extend) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_itam_cost_service.py` — golden table, reason precedence invariant, type guards, disposed/retired rule, duplicates, placeholder serials, sort order, `platform-admin` argument refused, static no-`$lookup`/`cached` scan
- [ ] `backend/tests/test_itam_cost_endpoints.py` — mocked-guard route tests (pattern: `_make_kpi_app` in `test_itam_reporting_kpis.py`), pagination, filters, 404
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
