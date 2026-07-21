---
phase: 43
slug: remediation-to-ticketing-bridge
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-21
---

# Phase 43 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (`backend/venv/bin/python -m pytest`) |
| **Config file** | none dedicated — plain `test_*.py` files under `backend/tests/` |
| **Quick run command** | `cd backend && venv/bin/python -m pytest tests/test_ticketing_bridge.py tests/test_remediation_workflow.py tests/test_tickets.py -q` |
| **Full suite command** | `cd backend && venv/bin/python -m pytest -q` |
| **Estimated runtime** | ~5-10s (quick, new file), ~50-60s (full backend suite per Phase 41/42 baseline) |

---

## Sampling Rate

- **After every task commit:** `cd backend && venv/bin/python -m pytest tests/test_ticketing_bridge.py tests/test_remediation_workflow.py tests/test_tickets.py -q`
- **After every plan wave:** `cd backend && venv/bin/python -m pytest -q`
- **Before `/gsd-verify-work`:** Full suite green; live browser click-through for the Create Ticket action, provider picker, and ticket-field display (no automated frontend test framework detected)
- **Max feedback latency:** ~60s

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Automated Command | File Exists | Status |
|---------|------|------|-------------|-------------------|-------------|--------|
| adapter | TBD | TBD | REM-01 | `pytest tests/test_ticketing_bridge.py -k adapter -x` | ❌ Wave 0 | ⬜ pending |
| create_ticket | TBD | TBD | REM-01 | `pytest tests/test_ticketing_bridge.py -k create_ticket -x` | ❌ Wave 0 | ⬜ pending |
| no_config | TBD | TBD | REM-01 | `pytest tests/test_ticketing_bridge.py -k no_config -x` | ❌ Wave 0 | ⬜ pending |
| dedup | TBD | TBD | REM-01 | `pytest tests/test_ticketing_bridge.py -k dedup -x` | ❌ Wave 0 | ⬜ pending |
| autocreate_nonfatal | TBD | TBD | REM-01 | `pytest tests/test_remediation_workflow.py -k autocreate_nonfatal -x` | ❌ Wave 0 | ⬜ pending |
| endpoint | TBD | TBD | REM-01 | `pytest tests/test_ticketing_bridge.py -k endpoint -x` | ❌ Wave 0 | ⬜ pending |
| status_check | TBD | TBD | REM-02 | `pytest tests/test_ticketing_bridge.py -k status_check -x` | ❌ Wave 0 | ⬜ pending |
| close_loop_dispatch | TBD | TBD | REM-02 | `pytest tests/test_ticketing_bridge.py -k close_loop_dispatch -x` | ❌ Wave 0 | ⬜ pending |
| close_loop_skip | TBD | TBD | REM-02 | `pytest tests/test_ticketing_bridge.py -k close_loop_skip -x` | ❌ Wave 0 | ⬜ pending |
| raw_db_registration | TBD | TBD | REM-02 | `pytest tests/test_ticketing_bridge.py -k raw_db_registration -x` | ❌ Wave 0 | ⬜ pending |
| close_loop_deleted_ticket | TBD | TBD | REM-02 (D-06) | `pytest tests/test_ticketing_bridge.py -k deleted_ticket -x` | ❌ Wave 0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky — Task ID/Plan/Wave columns filled once the planner assigns tasks; requirement→command mapping carried verbatim from 43-RESEARCH.md's Validation Architecture section.*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_ticketing_bridge.py` — new file, covers all REM-01/REM-02 rows above. Clone the `_mock_db()` factory from `tests/test_remediation_workflow.py`, extend with mocked `db.ticketing_configs`/`db.ticketing_log`.
- [ ] `backend/tests/test_remediation_workflow.py` — extend existing `_mock_db()` with a `db.compliance_remediation_tasks` scenario for the auto-create-on-critical/high/medium-priority hook inside `create_task` (revised 2026-07-21 — was high/critical only).
- [ ] Framework install: none — pytest/unittest.mock already present in `backend/venv`.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|--------------------|
| "Create Ticket" action + provider picker render in the remediation task view | REM-01 | No automated frontend test framework detected for `RemediationDashboard.tsx`/`RemediationTaskModal.tsx` | Open a remediation task, click Create Ticket, confirm provider picker appears if both Jira/ServiceNow configured, confirm ticket provider/ref/url display after creation |
| Auto-created ticket on high/critical priority task creation | REM-01 (D-01) | Requires a live Jira/ServiceNow sandbox credential to observe the real side effect, not just the mocked unit-test call | Create a new remediation task at critical priority with ticketing configured, confirm a ticket appears without clicking Create Ticket |
| Close-loop actually resolves the task when the real external ticket closes | REM-02 | Requires waiting for the polling interval (15-30 min) against a live Jira/ServiceNow sandbox instance — not reproducible in a hermetic unit test | Close the linked ticket in Jira/ServiceNow directly, wait one polling interval, confirm the remediation task auto-transitions to Resolved and a re-scan dispatch fires (same as manual resolution) |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (test_ticketing_bridge.py new; test_remediation_workflow.py extended)
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** planned 2026-07-21 — Task ID/Plan/Wave columns assigned once the planner emits actual plan/task IDs; live-sandbox auto-create and close-loop timing remain manual/UAT gates (no test Jira/ServiceNow instance in this environment).
