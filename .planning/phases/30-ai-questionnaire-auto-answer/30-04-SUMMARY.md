# Phase 30-04: Grounded answer-draft service (RAG + generation + insufficient-evidence fallback)
---
phase: 30-ai-questionnaire-auto-answer
plan: 04
date: 2026-07-10
summary: >
  Implemented the core logic for AI-powered questionnaire answer drafting.
  This included creating `questionnaire_answer_draft_service.py` to handle RAG-based
  retrieval, LLM generation, Pydantic validation of outputs, and a robust
  insufficient-evidence fallback mechanism. Drafts are now stored with `pending_review` status.
  `questionnaire_answer_draft_endpoints.py` was created to expose API endpoints
  for generating new drafts for a given question set and for listing existing drafts.
  Comprehensive unit tests were implemented in `test_questionnaire_answer_draft_service.py`,
  covering various scenarios including empty retrieval, BLOCKED/Error LLM responses,
  valid generation, and Pydantic validation rules for `AnswerDraft`.
  The Pydantic `AnswerDraft` model now correctly flags confident answers without
  cited evidence and handles LLM error strings, routing them to the insufficient-evidence fallback.

artifacts_created:
  - /home/user/enterprise-omni-agent-ai-platform/backend/questionnaire_answer_draft_service.py
  - /home/user/enterprise-omni-agent-ai-platform/backend/questionnaire_answer_draft_endpoints.py
  - /home/user/enterprise-omni-agent-ai-platform/backend/tests/test_questionnaire_answer_draft_service.py

key_findings:
  - The Pydantic `AnswerDraft` model was carefully refined to ensure
    grounding invariants are met, specifically requiring `source_evidence_ids`
    for any `confidence` level other than "insufficient_evidence".
  - Error handling for LLM generation (`BLOCKED:`/`Error:` prefixes and JSON parsing failures)
    now correctly routes to the `_insufficient_evidence_draft` fallback, preventing
    unsuitable content from being stored as an answer.
  - The `draft_answer_for_question` function ensures that all generated drafts,
    including insufficient-evidence fallbacks, are persisted to the database
    with `pending_review` status, adhering to the human-in-the-loop requirement.
---