---
audit_acknowledged:
  milestone: v4.1
  at: 2026-08-26
  gap_snapshot: "unknown::scenarios=0"
---

# UAT Report: Phase 30 — AI Questionnaire Auto-Answer

## Overview

Validation of AI-powered questionnaire auto-answer feature, including inbound intake, RAG integration, draft generation, and human review workflow.
**Completed 2026-07-14 by driving the running app** (uvicorn backend + Vite frontend + headless Chromium) as a signup-created Tenant Admin.

## Test Cases

| ID | Description | Result | Notes |
|----|-------------|--------|-------|
| 1 | Inbound Intake (Manual) | **Passed** | Via API and via dashboard form (title + one-question-per-line). |
| 2 | Inbound Intake (CSV/Excel Upload) | **Passed** | CSV upload via API and via the dashboard's per-set Upload button; question count grew 2→4 with row indices. |
| 3 | Draft Generation (API) | **Passed** | With no tenant evidence in the RAG store, generation returns a clean `insufficient_evidence` draft held for review — no hallucinated answer. |
| 4 | Draft Generation (UI) | **Passed** | "Generate draft answers" per set; drafts appear in the review queue with Insufficient-evidence banner. |
| 5 | Human Review Workflow (API) | **Passed** | Submit blocked pre-approval (409), approve with edited answer text, submit records `submitted_by`, double-submit blocked (409). |
| 6 | Human Review Workflow (UI) | **Passed** | Approve → Confirm Approve → status badge Approved → Mark Submitted → toast "Answer marked submitted". |
| 7 | Tenant Isolation (RAG) | Passed | Automated backend test `test_rag_service_tenant_isolation.py` (real ChromaDB). |
| 8 | Generation Controls (API) | Passed | Signature inspection and E2E test passes confirm parameters are plumbed through. |

## Defects found and fixed during UAT (commit 368f01d9)

1. **`_REVIEWER_ROLES` role vocabulary mismatch** — set contained `{admin, super_admin, compliance_reviewer}` but the platform assigns `Tenant Admin`/`Super Admin` at signup/seed: every real admin got 403 on review decisions. Backend set and the `QuestionnaireAnswerReviewPanel.tsx` copy both updated.
2. **`GET /pending-review` 500** — the duplicate `list_pending_drafts` in `questionnaire_answer_review_service.py` was missing the `_id` projection (5f78f43e only fixed the `draft_service` copy); ObjectId broke JSON serialization.
3. **Submit unreachable from the UI** — the review queue listed only `pending_review` drafts, but "Mark Submitted" renders only on `approved` drafts, so approving a draft removed it from the queue before it could be submitted. `GET /` now returns all tenant drafts; dashboard filters out `submitted`.

## Evidence

- Screenshots: scratchpad `shots/04-inbound-questionnaires.png` … `09-csv-uploaded.png` (session-local); `08-draft-submitted.png` shows Approved badge + "Answer marked submitted" toast + Reviews(1).
