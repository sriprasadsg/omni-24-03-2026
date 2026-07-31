---
phase: 42
slug: comment-threads-on-compliance-controls
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-21
---

# Phase 42 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.0 + pytest-asyncio (auto mode) |
| **Config file** | `pytest.ini` (repo root) |
| **Quick run command** | `cd backend && venv/bin/python -m pytest tests/test_control_comments.py -q` |
| **Full suite command** | `cd backend && venv/bin/python -m pytest -q` |
| **Estimated runtime** | ~5s (quick, new file), ~30-60s (full backend suite per Phase 40/41 baseline) |

---

## Sampling Rate

- **After every task commit:** `cd backend && venv/bin/python -m pytest tests/test_control_comments.py -q`
- **After every plan wave:** `cd backend && venv/bin/python -m pytest -q`
- **Before `/gsd-verify-work`:** Full suite green; live browser click-through for the comment panel render (no automated frontend test framework detected)
- **Max feedback latency:** ~60s

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 42-01 (role gate) | 01 | 1 | CMT-01 | Privilege escalation via role-check bypass | Server-side role re-check on every POST, never trust frontend | unit | `pytest tests/test_control_comments.py -k test_non_author_role_forbidden -q` | ❌ W0 | ⬜ pending |
| 42-01 (post+list) | 01 | 1 | CMT-01 | — | Reviewer/admin can post; comment persists and is retrievable | unit | `pytest tests/test_control_comments.py -k test_post_and_list_comment -q` | ❌ W0 | ⬜ pending |
| 42-01 (tenant isolation) | 01 | 1 | CMT-01 | Cross-tenant data disclosure via exempt collection | `control_comments` NOT on exemption allowlist; tenant A cannot see tenant B's comments | unit | `pytest tests/test_control_comments.py -k test_tenant_isolation -q` | ❌ W0 | ⬜ pending |
| 42-02 (mention notify) | 02 | 2 | CMT-01 | — | @mention in comment text triggers a `db.notifications` write (in-app) | unit | `pytest tests/test_control_comments.py -k test_mention_triggers_notification -q` | ❌ W0 | ⬜ pending |
| 42-02 (in-app only) | 02 | 2 | CMT-01 | — | @mention notification does NOT trigger email/sms/slack channel dispatch (D-02) | unit | `pytest tests/test_control_comments.py -k test_mention_is_in_app_only -q` | ❌ W0 | ⬜ pending |
| 42-03 (frontend render) | 03 | 3 | CMT-01 | Stored XSS via unescaped comment text | Comment appears in `FrameworkDetail.tsx`'s expanded control row; text rendered via `{comment.text}`, never `dangerouslySetInnerHTML` | manual | Live browser click-through: expand a control, post a comment, confirm it renders escaped | n/a (manual gate) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky — Task ID/Plan/Wave columns are provisional pending the planner's actual task breakdown; requirement/threat/command mapping carried verbatim from 42-RESEARCH.md's Validation Architecture + Security Domain sections.*

**Reference test for the role-gate shape to clone:** `backend/tests/test_evidence_review.py::test_non_reviewer_role_forbidden_from_decision` (lines 312-322) — `_make_user(role=...)` MagicMock + FastAPI `TestClient` with `dependency_overrides`, asserts `resp.status_code == 403`.

---

## Wave 0 Requirements

- [ ] `backend/tests/test_control_comments.py` — new file, covers all 5 automated CMT-01 test rows above. No existing test file covers control comments; role-gate shape clones from `test_evidence_review.py`.
- [ ] No new fixtures needed — `_make_user`/mock-db helpers copied inline from `test_evidence_review.py`'s existing pattern.
- [ ] Framework install: none — pytest/pytest-asyncio already installed in `backend/venv`.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|--------------------|
| Comment panel renders in `FrameworkDetail.tsx`'s expanded control row, mounted after `<ChainOfCustodyPanel>` | CMT-01 | No automated frontend test framework detected for this component | Expand a control in the Framework Detail view, confirm a comment panel is visible below the chain-of-custody panel, post a comment, confirm it appears immediately |
| @mention notification actually surfaces in the bell icon / `NotificationsDashboard` for the mentioned user | CMT-01 | End-to-end delivery through the UI notification surface is not covered by backend unit tests (those only assert the `db.notifications` write) | As user A, post a comment `@username` mentioning user B; log in as user B, confirm the bell icon shows a new notification referencing the comment |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (test_control_comments.py is new, created in Wave 1)
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** planned 2026-07-21 — Task ID/Plan/Wave columns are provisional (assigned for real once the planner emits actual plan/task IDs); frontend comment-panel render + notification-delivery end-to-end remain manual/UAT gates (no frontend test framework in repo).
