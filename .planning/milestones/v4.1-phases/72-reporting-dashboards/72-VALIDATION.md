---
phase: 72
slug: reporting-dashboards
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-16
---

# Phase 72 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (async, `httpx.AsyncClient`/`ASGITransport`) backend; vitest frontend |
| **Config file** | none — existing project pytest/vitest config covers new files |
| **Quick run command** | `backend/venv/bin/python -m pytest backend/tests/test_itam_reporting*.py -x` |
| **Full suite command** | `backend/venv/bin/python -m pytest` (backend) + `npx vitest run` + `npm run build` (frontend) |
| **Estimated runtime** | ~60s quick / full suite per existing project baseline |

---

## Sampling Rate

- **After every task commit:** Run `backend/venv/bin/python -m pytest backend/tests/test_itam_reporting*.py -x`
- **After every plan wave:** Run full backend suite + `npx vitest run` + `npm run build`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 72-01-T1 | 72-01 | 1 | ITAM-REP-02, ITAM-REP-03 | T-72-03, T-72-04, T-72-05, T-72-06 | Tracer: warranty report runs, exports to CSV, downloads tenant-safely; path traversal rejected | integration | `backend/venv/bin/python -m pytest backend/tests/test_itam_reporting_export.py -x` | ❌ created by this task | ⬜ pending |
| 72-01-T2 | 72-01 | 1 | ITAM-REP-02 | — | Reports tab empty/loading/error/partial states render per UI-SPEC E4 | component (vitest + RTL) | `npx vitest run src/__tests__/ITAMReportsPanel.test.tsx src/__tests__/ITAMConsole.test.tsx` | ❌ created by this task | ⬜ pending |
| 72-02-T1 | 72-02 | 2 | ITAM-REP-02 | T-72-02a | Asset-value, activity-log and overdue-audit reports match the existing finance/lifecycle figures | unit | `backend/venv/bin/python -m pytest backend/tests/test_itam_reporting_prebuilt.py -x` | ❌ created by this task | ⬜ pending |
| 72-02-T2 | 72-02 | 2 | ITAM-REP-02 | T-72-02b, T-72-02c | Licence utilisation + low-stock (reorderThreshold with fallback) reports; no licence secret column | unit | `backend/venv/bin/python -m pytest backend/tests/test_itam_reporting_prebuilt.py backend/tests/test_itam_license.py -x` | ❌ created by 72-02-T1 | ⬜ pending |
| 72-03-T1 | 72-03 | 2 | ITAM-REP-01 | T-72-01, T-72-02, T-72-07 | Closed operator vocabulary, boundary semantics, field allowlist, cross-tenant join safety | unit + integration | `backend/venv/bin/python -m pytest backend/tests/test_itam_reporting_builder.py -x` | ❌ created by this task | ⬜ pending |
| 72-03-T1b | 72-03 | 2 | Cross-tenant join safety | T-72-02 (Pitfall 4) | A custom report joining license/component/consumable data never returns another tenant's rows even when ids/keys collide | integration | `backend/venv/bin/python -m pytest backend/tests/test_itam_reporting_builder.py -k tenant_isolation -x` | ❌ created by 72-03-T1 | ⬜ pending |
| 72-03-T2 | 72-03 | 2 | ITAM-REP-01 | T-72-05 | Saved-report CRUD/preview/export gated by `manage:assets`; run-after-delete 404 | integration | `backend/venv/bin/python -m pytest backend/tests/test_itam_reporting_builder.py -k permission -x` | ❌ created by 72-03-T1 | ⬜ pending |
| 72-04-T1 | 72-04 | 2 | ITAM-REP-04 | T-72-04b | 4 KPIs compute correctly against seeded multi-status/multi-license data; tenant isolation on KPI aggregates | unit | `backend/venv/bin/python -m pytest backend/tests/test_itam_reporting_kpis.py -x` | ❌ created by this task | ⬜ pending |
| 72-04-T2 | 72-04 | 2 | ITAM-REP-04 | T-72-05, T-72-10 | `/api/itam/kpis` gated, tenant-scoped, generic 500 on failure | integration | `backend/venv/bin/python -m pytest backend/tests/test_itam_reporting_kpis.py -x` | ❌ created by 72-04-T1 | ⬜ pending |
| 72-05-T1 | 72-05 | 3 | ITAM-REP-03 | T-72-04c, T-72-11 | PDF export for both report kinds, full row set, tenant-owned download | integration | `backend/venv/bin/python -m pytest backend/tests/test_itam_reporting_export.py -x` | ✅ from 72-01 | ⬜ pending |
| 72-05-T2 | 72-05 | 3 | ITAM-REP-03 | T-72-06, T-72-08 | Excel export, identical row count/order across all three formats, sanitised cells | integration | `backend/venv/bin/python -m pytest backend/tests/test_itam_reporting_export.py -x` | ✅ from 72-01 | ⬜ pending |
| 72-06-T1 | 72-06 | 4 | ITAM-REP-01 | T-72-12 | Field+filter picker offers only catalogue fields and their legal operators | component (vitest + RTL) | `npx vitest run src/__tests__/ITAMReportsPanel.test.tsx` | ✅ from 72-01 | ⬜ pending |
| 72-06-T2 | 72-06 | 4 | ITAM-REP-01, ITAM-REP-02, ITAM-REP-03 | T-72-13 | Two-section tab, saved list + delete confirmation, three export buttons | component (vitest + RTL) | `npx vitest run src/__tests__/ITAMReportsPanel.test.tsx src/__tests__/ITAMConsole.test.tsx` | ✅ from 72-01 | ⬜ pending |
| 72-07-T1 | 72-07 | 5 | ITAM-REP-04 | T-72-15, T-72-16 | Four recharts tiles, honest no-data state, drill-down callback | component (vitest + RTL) | `npx vitest run src/__tests__/ITAMKpiPanel.test.tsx` | ❌ created by this task | ⬜ pending |
| 72-07-T2 | 72-07 | 5 | ITAM-REP-04 | — | KPI tile click drills into correct pre-built report / filtered asset view | component (vitest + RTL) | `npx vitest run src/__tests__/ITAMConsole.test.tsx src/__tests__/ITAMKpiPanel.test.tsx` | ✅ from 72-01 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*
*Task/Plan/Wave IDs filled in by `/gsd-plan-phase 72` against the seven-plan breakdown (2026-08-16). Every task carries an `<automated>` verify; no task depends on a test file that a later plan creates — each test file is created by the first task that needs it.*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_itam_reporting_builder.py` — covers ITAM-REP-01 (filter engine, save/list custom reports, admin-gate, cross-tenant join safety)
- [ ] `backend/tests/test_itam_reporting_prebuilt.py` — covers ITAM-REP-02 (all 6 pre-built reports)
- [ ] `backend/tests/test_itam_reporting_export.py` — covers ITAM-REP-03 (pdf/csv/xlsx generation + tenant-safe download)
- [ ] `backend/tests/test_itam_reporting_kpis.py` — covers ITAM-REP-04 backend
- [ ] `src/__tests__/ITAMKpiPanel.test.tsx` — covers ITAM-REP-04 frontend drill-down
- [ ] `src/__tests__/ITAMReportsPanel.test.tsx` — covers Reports tab rendering (pre-built list + custom builder sections, D-10)
- [ ] `backend/tests/itam_reporting_test_support.py` — shared fixture seeding assets+licenses+consumables+components together in one tenant for join tests (no existing fixture covers this cross-entity shape)

---

## Manual-Only Verifications

*All phase behaviors have automated verification per the Phase Requirements → Test Map above.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
