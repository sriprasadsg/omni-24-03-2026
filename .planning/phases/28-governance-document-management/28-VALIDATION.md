---
phase: 28
slug: governance-document-management
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-07
---

# Phase 28 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (`pytest.ini` at repo root) |
| **Config file** | `pytest.ini` |
| **Quick run command** | `cd backend && python -m pytest tests/test_governance_documents.py -x` |
| **Full suite command** | `cd backend && python -m pytest tests/ -q` |
| **Estimated runtime** | ~10-15 seconds (quick) |

---

## Sampling Rate

- **After every task commit:** `cd backend && python -m pytest tests/test_governance_documents.py -x`
- **After every plan wave:** `cd backend && python -m pytest tests/ -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

Task IDs are assigned by the planner; requirement-level rows below are the contract the planner must map tasks onto (per `28-RESEARCH.md` § Validation Architecture).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | DOC-01 | — | Create draft document, add version, submit for approval (delegates to `approval_service`), approval-resolution gates publish | unit + integration | `pytest tests/test_governance_documents.py -k "approval or version" -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | DOC-01 | T-28-01 | Tenant isolation — a document/approval in tenant A is invisible/403 to tenant B | unit | `pytest tests/test_governance_documents.py -k tenant -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | DOC-02 | T-28-02 | Sign endpoint captures typed name, consent, server-derived IP/UA/timestamp; rejects missing consent or empty typed name; never trusts client-supplied identity/IP/timestamp | unit | `pytest tests/test_governance_documents.py -k sign -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | DOC-02 | T-28-03 | Signed-PDF export produces a valid PDF containing signer name/timestamp, with `html.escape` applied to all user content (reproducing the CR-01 fix) | unit | `pytest tests/test_governance_documents.py -k pdf -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | DOC-01/02 | T-28-04 | Approval bypass prevention: sign/publish endpoints re-check live `approval_requests` status == "approved" before proceeding, not a stale local field | unit | `pytest tests/test_governance_documents.py -k approval_bypass -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_governance_documents.py` — new file; clone the `_col`/`_db`/`_user`/`_app` helper block from `backend/tests/test_automation_and_baa.py`
- [ ] Framework install: none — pytest already present and configured

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|--------------------|
| New Governance Documents dashboard is actually reachable from navigation, not just built | DOC-01 | This project has a 6-instance documented history (per STATE.md) of shipping dashboards that are never wired into `App.tsx`/`Sidebar.tsx`/`types.ts` navigation | Open the app, find "Governance & Compliance" in the sidebar, confirm a Governance Documents entry exists and opens the new dashboard |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
