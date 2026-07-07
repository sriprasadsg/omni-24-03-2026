---
phase: 31
slug: fair-risk-quantification
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-08
---

# Phase 31 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (`pytest.ini` at repo root, `asyncio_mode = auto`) |
| **Config file** | `pytest.ini` |
| **Quick run command** | `cd backend && python -m pytest tests/test_risk_fair_simulation.py -x` |
| **Full suite command** | `cd backend && python -m pytest tests/ -q` |

---

## Sampling Rate

- **After every task commit:** `cd backend && python -m pytest tests/test_risk_fair_simulation.py -x`
- **After every plan wave:** `cd backend && python -m pytest tests/ -q`
- **Before `/gsd-verify-work`:** Full suite green, plus a real `TestClient` HTTP call through `POST /api/risks/{id}/fair-simulation` (not just a direct call to `run_fair_simulation()`)
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| T-31-01 | 31-01 | 1 | FAIR-01 | — | Submitting valid FAIR inputs (LEF/LM min/likely/max) returns `fair_results` with mean/p10/p50/p90/exceedance_curve and persists on the risk doc | integration | `pytest tests/test_risk_fair_simulation.py -k valid_simulation -x` | ❌ W0 | ⬜ pending |
| T-31-01 | 31-01 | 1 | FAIR-01 | — | `min > likely` or `likely > max` for either LEF or LM returns 422, not an unhandled numpy ValueError→500 | unit | `pytest tests/test_risk_fair_simulation.py -k invalid_range -x` | ❌ W0 | ⬜ pending |
| T-31-01 | 31-01 | 1 | FAIR-01 | — | Iteration count (if client-exposed) is bounded — above-ceiling value returns 422 | unit | `pytest tests/test_risk_fair_simulation.py -k iteration_bound -x` | ❌ W0 | ⬜ pending |
| T-31-01 | 31-01 | 1 | FAIR-01 | — | Endpoint is tenant-scoped exactly like `update_risk`/`delete_risk` — a risk in tenant B is unreachable (404) from tenant A | unit | `pytest tests/test_risk_fair_simulation.py -k tenant_isolation -x` | ❌ W0 | ⬜ pending |
| T-31-01 | 31-01 | 1 | FAIR-01 | — | A risk with no `fair_inputs`/`fair_results` submitted still returns/persists its existing qualitative fields unchanged | unit | `pytest tests/test_risk_fair_simulation.py -k optional_no_regression -x` | ❌ W0 | ⬜ pending |
| T-31-01 | 31-01 | 1 | FAIR-01 | — | Monte Carlo output is statistically sane for a known-simple input (LEF fixed 1, LM fixed 100 → mean ≈ 100, low variance) | unit | `pytest tests/test_risk_fair_simulation.py -k math_sanity -x` | ❌ W0 | ⬜ pending |
| T-31-02 | 31-02 | 2 | FAIR-01 | — | `RiskFormModal.tsx` FAIR input fields + `RiskRegister.tsx` FAIR result display build and reach the existing risk-register nav path, no new nav entry needed | build + manual | `npm run build` | ✅ (existing files) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_risk_fair_simulation.py` — new file; clone the `_col`/`_db`/`_user`/`_app` helper block from `backend/tests/test_automation_and_baa.py` (same convention `26-03-PLAN.md`'s risk tests use)
- [ ] Framework install: none — pytest already present; numpy/pandas already declared dependencies

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|--------------------|
| FAIR input form and exceedance-curve display are reachable and usable from the existing Risk Register UI | FAIR-01 | Visual/interaction check on an existing, already-wired dashboard (not a new nav item, but a genuinely new sub-form) | Open Risk Register, edit a risk, enter FAIR inputs, run simulation, confirm the loss-exceedance summary renders sensibly |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (`test_risk_fair_simulation.py` created before any FAIR-01 assertion runs)
- [x] No watch-mode flags (pytest `-x`, no `--watch`)
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved (planner, 2026-07-08)
