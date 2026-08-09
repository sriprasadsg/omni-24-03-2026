---
phase: 26
slug: vendor-and-risk-data-completeness
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-06
---

# Phase 26 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (`pytest.ini` at repo root: `testpaths = . backend`, `asyncio_mode = auto`, FastAPI TestClient) |
| **Config file** | `pytest.ini` |
| **Quick run command** | `pytest backend/tests/test_dpa_endpoints.py backend/tests/test_vendor_subprocessors.py backend/tests/test_risk_inherent_residual.py -x` |
| **Full suite command** | `pytest` (from repo root) |
| **Estimated runtime** | ~15-20 seconds (quick) |

---

## Sampling Rate

- **After every task commit:** Run `pytest backend/tests/test_dpa_endpoints.py backend/tests/test_vendor_subprocessors.py backend/tests/test_risk_inherent_residual.py -x`
- **After every plan wave:** Run `pytest` (full suite)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

Task IDs are assigned by the planner; requirement-level rows below are the contract the planner must map tasks onto (per `26-RESEARCH.md` § Validation Architecture).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 26-01-T3 | 26-01 | 1 | VRISK-01 | — | DPA create starts in `draft`, unsigned | unit | `pytest backend/tests/test_dpa_endpoints.py::TestDPACreate -x` | ❌ W0 | ⬜ pending |
| 26-01-T3 | 26-01 | 1 | VRISK-01 | — | Single-party sign does NOT activate (mirrors a known BAA bug class) | unit | `pytest backend/tests/test_dpa_endpoints.py::TestDPASign::test_single_party_sign_does_not_activate -x` | ❌ W0 | ⬜ pending |
| 26-01-T3 | 26-01 | 1 | VRISK-01 | — | Both-parties-signed activates DPA | unit | `pytest backend/tests/test_dpa_endpoints.py::TestDPASign::test_both_parties_signed_activates -x` | ❌ W0 | ⬜ pending |
| 26-01-T3 | 26-01 | 1 | VRISK-01 | T-26-02 | Terminate sets status + respects tenant filter | unit | `pytest backend/tests/test_dpa_endpoints.py::TestDPATerminate -x` | ❌ W0 | ⬜ pending |
| 26-01-T3 | 26-01 | 1 | VRISK-01 | T-26-01 | Non-admin role forbidden from creating DPA (do not inherit BAA's ungated create_baa) | unit | `pytest backend/tests/test_dpa_endpoints.py::TestDPACreate::test_create_forbidden_for_non_admin -x` | ❌ W0 | ⬜ pending |
| 26-02-T3 | 26-02 | 1 | VRISK-02 | T-26-03 | Adding a subprocessor pushes to vendor's `subprocessors` array | unit | `pytest backend/tests/test_vendor_subprocessors.py::TestAddSubprocessor -x` | ❌ W0 | ⬜ pending |
| 26-02-T3 | 26-02 | 1 | VRISK-02 | T-26-03 | Removing a subprocessor pulls it from the array | unit | `pytest backend/tests/test_vendor_subprocessors.py::TestRemoveSubprocessor -x` | ❌ W0 | ⬜ pending |
| 26-02-T3 | 26-02 | 1 | VRISK-02 | T-26-04 | Subprocessor mutation respects tenant scope + RBAC | unit | `pytest backend/tests/test_vendor_subprocessors.py::TestSubprocessorRBAC -x` | ❌ W0 | ⬜ pending |
| 26-03-T3 | 26-03 | 1 | RISK-01 | — | `create_risk` populates both `risk_score`/`inherent_risk_score` and `residual_risk_score` | unit | `pytest backend/tests/test_risk_inherent_residual.py::TestRiskCreate -x` | ❌ W0 | ⬜ pending |
| 26-03-T3 | 26-03 | 1 | RISK-01 | — | `update_risk` recomputes residual score when residual inputs change | unit | `pytest backend/tests/test_risk_inherent_residual.py::TestRiskUpdate -x` | ❌ W0 | ⬜ pending |
| 26-03-T3 | 26-03 | 1 | RISK-01 | T-26-07 | Omitting residual inputs defaults residual == inherent (no silent risk overstatement/understatement) | unit | `pytest backend/tests/test_risk_inherent_residual.py::TestRiskDefaults -x` | ❌ W0 | ⬜ pending |
| 26-04-T2 | 26-04 | 2 | VRISK-02 | T-26-09 | Vendor detail modal is reachable and lists/adds/removes subprocessors + shows DPA status | manual + build | `npm run build` (+ human click-through) | ❌ W0 | ⬜ pending |
| 26-05-T2 | 26-05 | 2 | RISK-01 | T-26-11 | Residual Score column renders (legacy-safe) alongside the inherent Score; residual inputs submit | manual + build | `npm run build` (+ human click-through) | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_dpa_endpoints.py` — covers VRISK-01, reuse `_col`/`_db`/`_user`/`_app` helpers copied inline from `test_automation_and_baa.py` (this repo's convention: copy inline per-file, not import)
- [ ] `backend/tests/test_vendor_subprocessors.py` — covers VRISK-02 (first-ever test file for `vendor_service.py`/`vendor_endpoints.py`)
- [ ] `backend/tests/test_risk_inherent_residual.py` — covers RISK-01 (first-ever test file for `risk_service.py`/`risk_endpoints.py`)
- [ ] Framework install: none — pytest + TestClient + AsyncMock pattern already fully configured

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|--------------------|
| New vendor detail view (subprocessor list) is actually reachable from the Vendor Management dashboard, not just built | VRISK-02 | This project has a recurring, documented pattern (3 prior phases per STATE.md) of dashboards being built but never wired into `App.tsx`/`Sidebar.tsx` navigation — a human should click through and confirm reachability, not just trust that the component exists | Open the app, navigate to Vendor Management, click a vendor row, confirm a detail view opens showing subprocessors with add/remove controls |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
