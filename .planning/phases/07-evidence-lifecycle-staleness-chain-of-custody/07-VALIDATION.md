---
phase: 7
slug: evidence-lifecycle-staleness-chain-of-custody
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-21
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (backend) · npm run build (frontend — vitest times out) |
| **Config file** | `backend/pytest.ini` or `backend/pyproject.toml` (existing) |
| **Quick run command** | `cd backend && python -m pytest tests/test_evidence_lifecycle.py -x -q` |
| **Full suite command** | `cd backend && python -m pytest tests/ -x -q` |
| **Estimated runtime** | ~15 seconds (backend); `npm run build` ~30s (frontend) |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && python -m pytest tests/test_evidence_lifecycle.py -x -q`
- **After every plan wave:** Run `cd backend && python -m pytest tests/ -x -q && npm run build`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 45 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 1 | STALE-01 | T-07-01 / — | Automated evidence only flagged stale; manual evidence never stale | unit | `python -m pytest tests/test_evidence_lifecycle.py::test_staleness_flag -x -q` | ❌ W0 | ⬜ pending |
| 07-01-02 | 01 | 1 | STALE-02 | — | Threshold stored per-tenant; out-of-range values rejected 422 | unit | `python -m pytest tests/test_evidence_lifecycle.py::test_threshold_settings -x -q` | ❌ W0 | ⬜ pending |
| 07-01-03 | 01 | 2 | COC-01 | T-07-02 / — | CoC entry appended on create/update/delete; cross-tenant writes rejected | unit | `python -m pytest tests/test_evidence_lifecycle.py::test_coc_append -x -q` | ❌ W0 | ⬜ pending |
| 07-01-04 | 01 | 2 | COC-02 | T-07-03 / — | GET audit-log returns 403 for non-audit-read users | unit | `python -m pytest tests/test_evidence_lifecycle.py::test_coc_permission -x -q` | ❌ W0 | ⬜ pending |
| 07-02-01 | 02 | 3 | STALE-01 | — | N/A (UI render) | build | `npm run build` | ✅ | ⬜ pending |
| 07-02-02 | 02 | 3 | STALE-02 | — | N/A (UI settings form) | build | `npm run build` | ✅ | ⬜ pending |
| 07-02-03 | 02 | 3 | COC-02 | — | N/A (UI panel render) | build | `npm run build` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_evidence_lifecycle.py` — stubs for STALE-01, STALE-02, COC-01, COC-02

*Existing infrastructure covers frontend (npm run build as integration gate). Backend test file is new for this phase.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Stale badge renders amber on evidence rows older than threshold | STALE-01 | Live browser UI rendering with real timestamp data | Navigate to framework detail view; check evidence row with `collected_at` > 7 days ago shows amber "Stale" badge |
| CoC log panel shows/hides correctly | COC-02 | Requires `view:audit_log` permission in browser session | Log in as admin; open framework detail; expand a control; verify CoC panel expands/collapses |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 45s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
