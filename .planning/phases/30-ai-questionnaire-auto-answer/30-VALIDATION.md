---
phase: 30
slug: ai-questionnaire-auto-answer
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-07
---

# Phase 30 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (`pytest.ini` at repo root, `asyncio_mode = auto`) |
| **Config file** | `pytest.ini` |
| **Quick run command** | `cd backend && python -m pytest tests/test_questionnaire_answer_draft_service.py tests/test_questionnaire_answer_review_service.py -x` |
| **Full suite command** | `cd backend && python -m pytest tests/ -q` |
| **Eval (non-blocking, slower)** | `python backend/tests/eval_questionnaire_auto_answer.py --dataset backend/tests/fixtures/questionnaire_eval_set.json` (per 30-AI-SPEC.md Section 5 — not run on every PR) |

---

## Sampling Rate

- **After every task commit:** `cd backend && python -m pytest tests/test_questionnaire_answer_draft_service.py tests/test_questionnaire_answer_review_service.py -x`
- **After every plan wave:** `cd backend && python -m pytest tests/ -q`
- **Before `/gsd-verify-work`:** Full suite green, PLUS `test_rag_service_tenant_isolation.py` passing as a hard blocker on merging both the `rag_service.py` fix and any code calling it
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| T-30-01 | 30-01 | 1 | — | T1 | `rag_service.query()` for tenant A returns zero chunks tagged tenant B; pre-existing content re-tagged `tenantId: "global"` is visible to all tenants via `$or` filter | integration | `pytest tests/test_rag_service_tenant_isolation.py -x` | ❌ W0 | ⬜ pending |
| T-30-02 | 30-01 | 1 | RAG-01 | — | Excel/CSV upload endpoint parses question rows via `pandas`/`openpyxl` (cloning `compliance_framework_mgmt_endpoints.py`'s pattern); unmapped/ambiguous column layout returns 400, never silently guesses | unit | `pytest tests/test_questionnaire_inbound_service.py -k upload -x` | ❌ W0 | ⬜ pending |
| T-30-02 | 30-01 | 1 | RAG-01 | — | Manual question-entry endpoint creates a tenant-scoped inbound question set | unit | `pytest tests/test_questionnaire_inbound_service.py -k create -x` | ❌ W0 | ⬜ pending |
| T-30-03 | 30-02 | 2 | RAG-01 | — | `draft_answer_for_question()` returns `confidence: insufficient_evidence` with empty `answer_text` when `rag_service.query()` returns nothing | unit | `pytest tests/test_questionnaire_answer_draft_service.py -k insufficient_evidence -x` | ❌ W0 | ⬜ pending |
| T-30-03 | 30-02 | 2 | RAG-01 | — | `AnswerDraft.grounded_or_flagged` validator rejects a confident answer with zero `source_evidence_ids` | unit | `pytest tests/test_questionnaire_answer_draft_service.py -k grounded_or_flagged -x` | ❌ W0 | ⬜ pending |
| T-30-04 | 30-03 | 2 | RAG-02 | T3 | A direct `pending_review → submitted` API/DB call is rejected (mandatory-review-gate integrity) | integration | `pytest tests/test_questionnaire_answer_review_service.py -k submit_bypass_rejected -x` | ❌ W0 | ⬜ pending |
| T-30-04 | 30-03 | 2 | RAG-02 | — | Review-decision endpoint requires reviewer role (`_REVIEWER_ROLES`-equivalent); a non-reviewer role gets 403 | unit | `pytest tests/test_questionnaire_answer_review_service.py -k rbac -x` | ❌ W0 | ⬜ pending |
| T-30-04 | 30-03 | 2 | RAG-02 | T5 | `reviewer_id`/`decided_by` is always server-derived from `current_user`, never accepted from request body | unit | `pytest tests/test_questionnaire_answer_review_service.py -k reviewer_identity_server_derived -x` | ❌ W0 | ⬜ pending |
| T-30-04 | 30-03 | 2 | RAG-02 | — | Every `approved` record has non-null `reviewer_id`, `decided_at`, and both `original_answer_text`/final `answer_text` present for diffing | unit | `pytest tests/test_questionnaire_answer_review_service.py -k reviewability_fields -x` | ❌ W0 | ⬜ pending |
| T-30-05 | 30-04 | 3 | RAG-01/02 | — | End-to-end: upload/create question → draft → review → approve, via `TestClient` HTTP calls (not module-level function calls) — catches the `response: Response` class of bug unit tests structurally cannot (Phase 25 precedent) | integration | `pytest tests/test_questionnaire_auto_answer_e2e.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_rag_service_tenant_isolation.py` — new file; single highest-priority test, blocks everything else touching `rag_service.query()`
- [ ] `backend/tests/test_questionnaire_inbound_service.py` — new file; covers both manual question-entry CRUD and Excel/CSV upload+parsing
- [ ] `backend/tests/test_questionnaire_answer_draft_service.py` — new file; clone `tests/test_evidence_review.py`'s `_make_user`/`_make_mock_db` helper-block convention
- [ ] `backend/tests/test_questionnaire_answer_review_service.py` — new file; clone `evidence_review_service.py`'s test shape directly (near-identical state machine)
- [ ] `backend/tests/test_questionnaire_auto_answer_e2e.py` — new file; `TestClient`-based, full create→draft→review→approve path over real HTTP
- [ ] `backend/tests/fixtures/questionnaire_eval_set.json` — new file; 15-example reference dataset per AI-SPEC Section 5, labeled during implementation
- [ ] Framework install: `pip install -r backend/requirements-eval.txt` (new file: `ragas==0.4.3`, `arize-phoenix==17.20.0`, `opentelemetry-sdk==1.43.0`) — opt-in eval tooling, not a runtime dependency

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|--------------------|
| New question-entry/upload UI and draft-review UI are actually reachable from navigation | RAG-01/RAG-02 | This project has a documented history of shipping dashboards never wired into `App.tsx`/`Sidebar.tsx` | Log in, find the inbound-questionnaire entry point in the sidebar, upload a sample .xlsx, confirm drafts appear in a review queue with approve/reject actions |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (5 requirement-mapped tasks across 4 plans; 9 test rows)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (6 new test files + 1 fixture created before any assertion runs)
- [x] No watch-mode flags (pytest `-x`, no `--watch`)
- [x] Feedback latency < 30s (backend suite ~10-15s; eval harness and manual UI check are phase-gate only)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved (planner, 2026-07-07)
