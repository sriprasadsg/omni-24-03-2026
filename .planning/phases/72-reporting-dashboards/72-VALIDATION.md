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
| 72-TBD | TBD | TBD | ITAM-REP-01 | — | Custom filter build+save, closed operator set, tenant-shared visibility | unit + integration | `backend/venv/bin/python -m pytest backend/tests/test_itam_reporting_builder.py -x` | ❌ Wave 0 | ⬜ pending |
| 72-TBD | TBD | TBD | ITAM-REP-01 | — | Custom report gated by admin permission (`manage:assets`), not accessible to `view:itam`-only role | integration | `backend/venv/bin/python -m pytest backend/tests/test_itam_reporting_builder.py -k permission -x` | ❌ Wave 0 | ⬜ pending |
| 72-TBD | TBD | TBD | ITAM-REP-02 | — | All 6 pre-built reports return correct rows against seeded data, including reused overdue-audit query | unit | `backend/venv/bin/python -m pytest backend/tests/test_itam_reporting_prebuilt.py -x` | ❌ Wave 0 | ⬜ pending |
| 72-TBD | TBD | TBD | ITAM-REP-03 | — | PDF/CSV/Excel export produces downloadable file for both custom and pre-built reports; download route rejects path traversal and cross-tenant filenames | integration | `backend/venv/bin/python -m pytest backend/tests/test_itam_reporting_export.py -x` | ❌ Wave 0 | ⬜ pending |
| 72-TBD | TBD | TBD | ITAM-REP-04 | — | 4 KPIs compute correctly against seeded multi-status/multi-license data; tenant isolation on KPI aggregates | unit | `backend/venv/bin/python -m pytest backend/tests/test_itam_reporting_kpis.py -x` | ❌ Wave 0 | ⬜ pending |
| 72-TBD | TBD | TBD | ITAM-REP-04 | — | KPI tile click drills into correct pre-built report / filtered asset view | component (vitest + RTL) | `npx vitest run src/__tests__/ITAMKpiPanel.test.tsx` | ❌ Wave 0 | ⬜ pending |
| 72-TBD | TBD | TBD | Cross-tenant join safety | Pitfall 4 | A custom report joining license/component/consumable data never returns another tenant's rows even when ids/keys collide | integration | `backend/venv/bin/python -m pytest backend/tests/test_itam_reporting_builder.py -k tenant_isolation -x` | ❌ Wave 0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*
*Task/Plan/Wave IDs are TBD — the planner fills these in against the actual task breakdown.*

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
