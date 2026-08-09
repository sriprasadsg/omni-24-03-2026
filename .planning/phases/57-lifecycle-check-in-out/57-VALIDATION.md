---
phase: 57
slug: lifecycle-check-in-out
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-04
---

# Phase 57 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (`@pytest.mark.asyncio`), `httpx.AsyncClient`/`ASGITransport` for endpoint-level tests |
| **Config file** | none — no `pytest.ini`/`pyproject.toml [tool.pytest]` section; pytest-asyncio auto-mode presumed active per `test_itam_foundation.py` precedent |
| **Quick run command** | `backend/venv/bin/python -m pytest backend/tests/test_itam_lifecycle.py -q` |
| **Full suite command** | `backend/venv/bin/python -m pytest backend/tests -q` |
| **Estimated runtime** | ~60 seconds |

---

## Sampling Rate

- **After every task commit:** Run `backend/venv/bin/python -m pytest backend/tests/test_itam_lifecycle.py -q`
- **After every plan wave:** Run `backend/venv/bin/python -m pytest backend/tests -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | ITAM-LIFE-02 | — | Checkout succeeds when `lifecycleStatus == deployable`; rejected (409) otherwise | unit | `pytest backend/tests/test_itam_lifecycle.py -k checkout -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ITAM-LIFE-02 | — | Checkout to a nonexistent user/location returns 400 | unit | `pytest backend/tests/test_itam_lifecycle.py -k checkout_target -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ITAM-LIFE-02 | — | Concurrent checkout requests on the same asset — only one succeeds (race test) | unit | `pytest backend/tests/test_itam_lifecycle.py -k concurrent -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ITAM-LIFE-03 | — | Checkin returns `lifecycleStatus` to `deployable` and clears assignment fields | unit | `pytest backend/tests/test_itam_lifecycle.py -k checkin -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ITAM-LIFE-04 | — | Every checkout/checkin writes exactly one `assignment_history` entry; no update/delete function exists on the history module | unit | `pytest backend/tests/test_itam_lifecycle.py -k history -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ITAM-LIFE-04 | — | History is tenant-isolated (cross-tenant read returns empty, not another tenant's rows) | unit | `pytest backend/tests/test_itam_lifecycle.py -k history_tenant_isolation -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ITAM-LIFE-05 | — | Marking an asset audited sets `lastAuditedAt`; overdue report excludes it until 12 months later | unit | `pytest backend/tests/test_itam_lifecycle.py -k audit_mark -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ITAM-LIFE-05 | — | Overdue report includes never-audited assets whose `createdAt` is >12 months old | unit | `pytest backend/tests/test_itam_lifecycle.py -k overdue -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | ITAM-LIFE-02/03 | T-security-rbac | Endpoints reject callers without `manage:assets` permission (403) | unit | `pytest backend/tests/test_itam_lifecycle.py -k rbac -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | (cross-cutting) | T-security-status-collision | Neither checkout nor checkin ever writes the `status` key (agent-liveness field) | unit | `pytest backend/tests/test_itam_lifecycle.py -k does_not_write_status -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*
*Task ID / Plan / Wave columns are TBD until the planner assigns tasks — will be filled by `/gsd-validate-phase` after PLAN.md files exist.*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_itam_lifecycle.py` — new file, covers all rows above; reuse `MockTenantIsolatedDatabase`/`MockTenantIsolatedCollection`/`_make_col` fixtures from `backend/tests/test_itam_foundation.py` (promote to `backend/tests/conftest.py` only if a second file needs them and no equivalent already exists there)
- [ ] Framework install: none — pytest/pytest-asyncio already installed and exercised by `test_itam_foundation.py`

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
