---
phase: 55
slug: advanced-threat-detection
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-03
---

# Phase 55 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (`asyncio_mode` / `pytestmark = pytest.mark.asyncio`), run via `backend/venv/bin/python -m pytest` |
| **Config file** | none dedicated — repo-wide convention, no `pytest.ini` / `pyproject.toml [tool.pytest]` section; tests use `pytestmark = pytest.mark.asyncio` per-file |
| **Quick run command** | `backend/venv/bin/python -m pytest backend/tests/test_remediation_guards.py backend/tests/test_remediation_playbook.py -q` |
| **Full suite command** | `cd backend && venv/bin/python -m pytest -q` |
| **Estimated runtime** | ~baseline 1343 passed / 3 pre-existing unrelated fails as of 2026-07-22 — re-baseline at phase start since Phases 46-53 landed since |

---

## Sampling Rate

- **After every task commit:** Run `backend/venv/bin/python -m pytest backend/tests/test_remediation_guards.py backend/tests/test_remediation_playbook.py backend/tests/test_webhook_signing.py -q`
- **After every plan wave:** Run `cd backend && venv/bin/python -m pytest -q`
- **Before `/gsd-verify-work`:** Full suite must be green (modulo the same pre-existing, documented, unrelated failures)
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

*Task IDs are assigned by `/gsd-plan-phase`'s planner (not yet run at VALIDATION.md seed time). The requirement-level test map below is known from RESEARCH.md and will be attached to specific Task IDs once plans exist — populate the Task ID / Plan / Wave columns at planning/validate-phase time.*

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| — | — | — | INT-04 | — | `SiemEngine` correlation extension ingests native findings and creates a `security_cases` doc when a `siem_rules` condition matches | unit | `pytest backend/tests/test_siem_engine.py -x` | ❌ W0 | ⬜ pending |
| — | — | — | INT-04 | — | Correlation reads are bounded (never unbounded `.find({})` scans) | unit | same file, assert `.to_list(length=N)` cap via mock call args | ❌ W0 | ⬜ pending |
| — | — | — | AUT-03 | — | `select_playbook()` new `anomaly` branch: `shadow_ai_detected` + real `agent_id` → `kill_process`; anything else → `None` | unit | `pytest backend/tests/test_remediation_playbook.py -k anomaly -x` | ❌ W0 | ⬜ pending |
| — | — | — | AUT-03 | — | New UEBA→`remediate()` call site fires exactly once per anomalous event, deduped via `ResponseOrchestrator.is_duplicate_task`, and NEVER bypasses the destructive-playbook approval gate | unit | `pytest backend/tests/test_ueba_remediation_trigger.py -x` | ❌ W0 | ⬜ pending |
| — | — | — | AUT-03 | — | Same approval/dry-run/lease/audit path as Phase 53 (no bypass) | integration | `pytest backend/tests/test_remediation_guards.py -x` (existing, re-run for regression) | ✅ exists | ⬜ pending |
| — | — | — | COMM-01 | — | New OCSF-formatted webhook payloads use `class_uid=2004, category_uid=2`, dispatched via `asyncio.create_task` (never awaited inline) | unit | `pytest backend/tests/test_webhook_signing.py -k ocsf -x` | ❌ W0 | ⬜ pending |
| — | — | — | COMM-01 | — | Webhook delivery failure does not raise/propagate into the calling correlation/anomaly/remediation code path | unit | same file, mock `httpx.AsyncClient.post` to raise, assert caller doesn't except | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_siem_engine.py` — covers INT-04 (no test file for `siem_engine.py` exists today — zero direct test coverage currently)
- [ ] `backend/tests/test_ueba_remediation_trigger.py` — covers AUT-03's new call site (dedup, approval-gate-preserving, fire-and-forget dispatch)
- [ ] Extend `backend/tests/test_remediation_playbook.py` — covers the new `select_playbook()` anomaly branch
- [ ] Extend `backend/tests/test_webhook_signing.py` (or new `test_soc_integration.py`) — covers COMM-01's OCSF shape + fire-and-forget dispatch
- [ ] No framework install needed — pytest/pytest-asyncio already present and used throughout `backend/tests/`

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
