---
phase: 44
slug: remediation-sla-escalation
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-21
---

# Phase 44 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (`pytest.ini`, asyncio mode `auto`) |
| **Config file** | `pytest.ini` (repo root) |
| **Quick run command** | `cd backend && venv/bin/python -m pytest tests/test_compliance_remediation_sla.py -v` |
| **Full suite command** | `cd backend && venv/bin/python -m pytest -q` |
| **Estimated runtime** | ~5-10s (quick, new file), ~50-60s (full backend suite per Phase 43 baseline) |

---

## Sampling Rate

- **After every task commit:** `cd backend && venv/bin/python -m pytest tests/test_compliance_remediation_sla.py -v`
- **After every plan wave:** `cd backend && venv/bin/python -m pytest -q`
- **Before `/gsd-verify-work`:** Full suite green; live browser click-through for the SLA badge and escalation-history panel (no automated frontend test framework detected)
- **Max feedback latency:** ~60s

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Automated Command | File Exists | Status |
|---------|------|------|-------------|-------------------|-------------|--------|
| compute_sla | TBD | TBD | SLA-01 | `pytest tests/test_compliance_remediation_sla.py -k compute_sla -x` | ❌ Wave 0 | ⬜ pending |
| run_sla_pass | TBD | TBD | SLA-01 | `pytest tests/test_compliance_remediation_sla.py -k run_sla_pass -x` | ❌ Wave 0 | ⬜ pending |
| raw_db_registration | TBD | TBD | SLA-01 | `pytest tests/test_compliance_remediation_sla.py -k raw_db_registration -x` | ❌ Wave 0 | ⬜ pending |
| escalation_history | TBD | TBD | SLA-02 | `pytest tests/test_compliance_remediation_sla.py -k escalation_history -x` | ❌ Wave 0 | ⬜ pending |
| tenant_scope | TBD | TBD | SLA-02 | `pytest tests/test_compliance_remediation_sla.py -k tenant_scope -x` | ❌ Wave 0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky — Task ID/Plan/Wave columns filled once the planner assigns tasks.*

**Reference test for the mock-db shape to clone:** `backend/tests/test_ticketing_bridge.py`'s `_mock_db()` factory (Phase 43 precedent, same collection).

---

## Wave 0 Requirements

- [ ] `backend/tests/test_compliance_remediation_sla.py` — new file, covers all 5 rows above. Clone `_mock_db()` from `test_ticketing_bridge.py`.
- [ ] Framework install: none — pytest/pytest-asyncio already installed.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|--------------------|
| SLA badge renders correctly on the remediation dashboard | SLA-01 | No automated frontend test framework for `RemediationDashboard.tsx` | View the remediation dashboard, confirm ok/at_risk/breached badges render with correct colors per task |
| Escalation history panel renders in the task modal | SLA-02 | No automated frontend test framework for `RemediationTaskModal.tsx` | Open a task with escalation history, confirm an append-only, timestamped list renders (no edit/delete controls) |
| Escalation notification actually surfaces in the bell icon for assignee + tenant admins | SLA-01 (D-03) | End-to-end delivery through the UI notification surface isn't covered by backend unit tests (those only assert the `send_alert` call) | Force a task past due_date, wait one scheduler pass, confirm both the assignee and a tenant admin see a new bell-icon notification |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (test_compliance_remediation_sla.py is new)
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** planned 2026-07-21 — Task ID/Plan/Wave columns provisional pending planner's task breakdown; frontend + live-notification-delivery remain manual/UAT gates.
