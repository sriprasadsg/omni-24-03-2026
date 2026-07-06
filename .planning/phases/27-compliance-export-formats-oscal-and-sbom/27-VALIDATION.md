---
phase: 27
slug: compliance-export-formats-oscal-and-sbom
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-06
---

# Phase 27 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (`pytest.ini` at repo root, `asyncio_mode = auto`) |
| **Config file** | `pytest.ini` |
| **Quick run command** | `pytest backend/tests/test_oscal_export.py backend/tests/test_container_sbom_export.py -x` |
| **Full suite command** | `pytest backend/tests -x` |
| **Estimated runtime** | ~10-15 seconds (quick) |

---

## Sampling Rate

- **After every task commit:** `pytest backend/tests/test_oscal_export.py backend/tests/test_container_sbom_export.py -x`
- **After every plan wave:** `pytest backend/tests -x`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

Task IDs are assigned by the planner; requirement-level rows below are the contract the planner must map tasks onto (per `27-RESEARCH.md` § Validation Architecture).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | EXP-01 | — | `GET /api/oscal/assessment-results?framework_id=X` returns a structurally-valid OSCAL assessment-results document (uuid, metadata required fields, results[] with reviewed-controls + findings) | unit | `pytest backend/tests/test_oscal_export.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | EXP-01 | T-27-01 | Tenant isolation: caller from tenant A cannot pull framework data scoped to tenant B | unit | `pytest backend/tests/test_oscal_export.py -x -k tenant` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | EXP-02 | — | `GET /api/container/results/{scan_id}/sbom` returns valid CycloneDX 1.6 JSON (bomFormat/specVersion/components/vulnerabilities, no duplicate bom-refs) | unit | `pytest backend/tests/test_container_sbom_export.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | EXP-02 | T-27-02 | Simulated scan results are flagged, not presented as authoritative evidence | unit | `pytest backend/tests/test_container_sbom_export.py -x -k simulated` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_oscal_export.py` — covers EXP-01, follow the `TestClient` + `AsyncMock` DB mocking pattern already established in `backend/tests/test_bundles_and_reports.py`
- [ ] `backend/tests/test_container_sbom_export.py` — covers EXP-02, mock `db._db.container_scan_results.find_one` (note: `container_scanner_service.py` uses the raw `db._db` accessor, not the tenant-isolated wrapper)
- [ ] Framework install: none — pytest + AsyncMock already fully set up project-wide

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
