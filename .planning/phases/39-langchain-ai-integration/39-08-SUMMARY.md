---
phase: 39-langchain-ai-integration
plan: 08
subsystem: ai
tags: [langchain, langgraph, create_agent, rag, pydantic, citation-validation, questionnaire, rag-02]

# Dependency graph
requires:
  - phase: 39-langchain-ai-integration (39-03)
    provides: ai_orchestration/schemas.py (CitedAnswer, Citation) + validators.py (validate_citations)
  - phase: 39-langchain-ai-integration (39-04)
    provides: ai_orchestration/models.py (build_model_for_tenant, model_provenance, ROUTER_STRUCTURED_OUTPUT_PASSTHROUGH)
  - phase: 39-langchain-ai-integration (39-05)
    provides: ai_orchestration/tools/retrieval.py (make_search_evidence), prompts.py, guardrails.py, decision_log.py
provides:
  - ai_orchestration/agents/questionnaire.py — create_agent questionnaire draft generation with CitedAnswer + citation validation + guardrails
  - questionnaire_answer_draft_service.py shim preserving draft_answer_for_question's contract + Mongo shape + RAG-02 gate
affects: [39-09 narrative migration, 39-11/39-12 eval dimensions]

tech-stack:
  added: []
  patterns:
    - "create_agent + ToolStrategy(CitedAnswer) structured output, mirroring agents/auditor.py's router-passthrough-FAIL handling"
    - "Agent module returns a plain dataclass (DraftResult) rather than writing to Mongo — persistence + RAG-02 gate stay exclusively in the shim"

key-files:
  created:
    - backend/ai_orchestration/agents/questionnaire.py
    - backend/tests/test_questionnaire_agent.py
  modified:
    - backend/questionnaire_answer_draft_service.py
    - backend/tests/test_questionnaire_auto_answer_e2e.py

key-decisions:
  - "DraftResult carries retrieved_evidence (raw RAG chunks) in addition to the plan's literal field list, so the shim can build its pre-existing sourceEvidence Mongo field without a second RAG query"
  - "Citation resolution for questionnaire answers uses the same validate_citations (39-03) as the auditor surface, which only resolves chunk_id against control_evidence/asset_compliance Mongo collections — not ChromaDB ids. Since questionnaire evidence comes from rag_service (Chroma), and this surface (per plan scope) only gets the search_evidence tool (no Mongo-backed evidence tool like the auditor's get_control_evidence), most real citations will not resolve and will conservatively downgrade to insufficient_evidence. This is fail-closed by design (never a fabricated confident answer) and RAG-02's pending_review gate means every draft is human-reviewed regardless; flagged here as a known limitation of the current architecture, not fixed (would require a new Mongo-backed evidence tool for this surface — an architectural change out of this plan's scope)."
  - "AnswerDraft re-exported from the shim as an alias for the shared CitedAnswer schema for backward compatibility with any caller still importing the old type name"

requirements-completed: [AISPEC-39-S4, AISPEC-39-S4b, AISPEC-39-S5, AISPEC-39-S6, AISPEC-39-S7]

duration: ~35min
completed: 2026-07-18
status: complete
---

# Phase 39 Plan 08: Questionnaire create_agent Migration Summary

**Questionnaire auto-answer surface migrated onto create_agent + CitedAnswer structured output with citation validation, guardrails, and provenance — the hand-rolled JSON-parse path is gone, and the RAG-02 pending_review gate is preserved by construction in a shim that never writes "submitted".**

## Performance

- **Duration:** ~35 min
- **Tasks:** 3
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments

- `ai_orchestration/agents/questionnaire.py`: `generate_draft(question_id, question_text, tenant_id, db, question_set_id=None)` builds a per-tenant `create_agent` with the tenant-closed `search_evidence` tool and `QUESTIONNAIRE_SYSTEM_PROMPT`, requesting `CitedAnswer` structured output via `ToolStrategy` (router-passthrough-FAIL decision from 39-02/39-04). Retrieved RAG evidence is PII-scrubbed before it reaches the model. Guardrail input/output/cross-tenant scans wrap the agent call. Every returned answer is run through the shared `validate_citations` (39-03); unresolvable citations, guardrail blocks, agent failures, and no-retrieved-evidence questions all resolve to `confidence="insufficient_evidence"` — never a fabricated confident claim. Fallback-provenance confident answers are flagged `needs_review=True`. Every outcome is logged via `log_ai_decision`; span attributes attached (tenant_id, surface="questionnaire", PROMPT_VERSION, model_provenance). The module never writes to Mongo.
- `questionnaire_answer_draft_service.py` rewritten as a thin shim: `draft_answer_for_question` keeps its exact signature and delegates generation to `generate_draft`, then builds the identical `questionnaire_answer_drafts` Mongo document (id, tenantId, questionSetId, questionId, questionText, answerText, original_answer_text, confidence, sourceEvidenceIds, sourceEvidence, status, created_at, updated_at) and always writes `status="pending_review"` — the RAG-02 human-approval gate is preserved by construction; the module contains zero occurrences of the literal `"submitted"`. `list_pending_drafts`/`list_drafts`/`get_draft`/`update_draft_status` unchanged.
- 14 hermetic unit tests added (`backend/tests/test_questionnaire_agent.py`, `-k agent`/`-k shim`) covering: answerable-question happy path, no-evidence → `insufficient_evidence` with empty `source_evidence_ids`, unresolvable-citation downgrade, input/output guardrail blocks, agent-invocation errors, fallback-provenance `needs_review` flagging, missing-structured-response handling, and the shim's exact Mongo document shape + the never-"submitted" guard (asserted directly against the module source, not just grep). Citation resolution runs for real against a small mocked db (mirrors `test_auditor_agent.py`'s own convention) so the validator wiring is actually exercised.

## Task Commits

Each task was committed atomically:

1. **Task 1: create_agent questionnaire draft generation (agents/questionnaire.py)** - `52bc693` (feat)
2. **Task 2: questionnaire_answer_draft_service.py shim (contract + Mongo shape + RAG-02 gate)** - `e98ee0e` (feat)
3. **Task 3: Questionnaire agent + shim unit tests** - `cf515cc` (test) — also includes the Rule 1 retarget of `tests/test_questionnaire_auto_answer_e2e.py`'s mocks (see Deviations)

**Plan metadata:** (this commit)

## Files Created/Modified

- `backend/ai_orchestration/agents/questionnaire.py` - create_agent questionnaire draft generation (346 lines)
- `backend/questionnaire_answer_draft_service.py` - shim preserving contract + Mongo shape + RAG-02 gate (145 lines)
- `backend/tests/test_questionnaire_agent.py` - 14 hermetic unit tests (427 lines)
- `backend/tests/test_questionnaire_auto_answer_e2e.py` - mock boundary retargeted from removed `rag_service`/`ai_service` module attributes onto `generate_draft`

## Decisions Made

- `DraftResult` (the agent's return type) carries `retrieved_evidence` (the raw RAG chunks) in addition to the plan's literal field list (`answer_text`, `confidence`, `source_evidence_ids`, `provenance`, `needs_review`) — needed so the shim can build its pre-existing `sourceEvidence` Mongo field without issuing a second, redundant RAG query. Documented as an intentional, minimal extension to the plan's return-object description.
- `AnswerDraft` is re-exported from the shim as an alias for the shared `CitedAnswer` schema (39-03), per the plan's "keep it importable" guidance — no other file in the codebase actually imports it, so this is a low-cost backward-compat guarantee rather than dead weight.
- Citation resolution architecture limitation (see frontmatter `key-decisions` for full detail): `validate_citations` resolves `chunk_id` only against `control_evidence`/`asset_compliance` Mongo collections, not ChromaDB ids, and this surface (per plan scope) only has the `search_evidence` RAG tool — no Mongo-backed evidence tool like the auditor's `get_control_evidence`. In practice this means most real-world questionnaire citations will fail to resolve and downgrade to `insufficient_evidence`. This is the correct fail-closed behavior per the plan's must_haves ("never a fabricated confident answer") and every draft is human-reviewed regardless (RAG-02), so it was not treated as a blocking defect — flagged here for a future plan to consider adding a Mongo-backed evidence tool to this surface if auto-answer acceptance rates need improving.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Retargeted `tests/test_questionnaire_auto_answer_e2e.py`'s mocks onto the new agent boundary**
- **Found during:** Task 3 (verifying no regression from the shim rewrite)
- **Issue:** This pre-existing Phase 30 e2e test patched `questionnaire_answer_draft_service.rag_service` and `.ai_service` — both module attributes were removed by Task 2's shim rewrite (generation now delegates entirely to `ai_orchestration.agents.questionnaire.generate_draft`). All 3 of the file's HTTP-pipeline tests failed with `AttributeError: module does not have the attribute 'rag_service'`.
- **Fix:** Retargeted `_pipeline_patches` to patch `questionnaire_answer_draft_service.generate_draft` directly with a canned `DraftResult`, since this file's actual job is exercising the HTTP `generate -> review -> approve -> submit` pipeline and the T3 submit-bypass guard — draft-generation internals (citation validation, guardrails, hallucination downgrade) are now covered by the new hermetic `test_questionnaire_agent.py`. Updated `test_generate_insufficient_evidence_when_rag_empty` and `test_generate_hallucination_guard` to pass the appropriate canned confidence/answer_text through the same helper rather than patching a JSON-string LLM response that no longer exists.
- **Files modified:** `backend/tests/test_questionnaire_auto_answer_e2e.py`
- **Verification:** `backend/venv/bin/python -m pytest tests/test_questionnaire_auto_answer_e2e.py -q` → 4 passed (was 4 passed before this plan's changes; confirmed identical pass count after the fix).
- **Committed in:** `cf515cc` (part of the Task 3 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1)
**Impact on plan:** Necessary to keep a pre-existing, out-of-scope test file green after this plan's in-scope shim rewrite removed the module attributes it patched. No scope creep — the fix only retargets mock boundaries, it does not change what the e2e file asserts about the HTTP pipeline.

## Issues Encountered

None beyond the deviation above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `ai_orchestration/agents/questionnaire.py` and its `DraftResult` dataclass are ready for 39-09 (narrative) to follow the same `create_agent` + `validate_citations` + guardrails + provenance + `log_ai_decision` pattern.
- Full backend suite: 1091 passed / 23 skipped / 2 failed (both pre-existing and unrelated to this plan's 4 files — `test_e2e_integration.py::test_golden_path_evidence_to_remediation` and `test_rust_heartbeat_parity.py::test_rust02_and_rust03_db_calls`, per the sequential-executor briefing).
- Known limitation carried forward (not a blocker): questionnaire citation resolution against RAG-sourced evidence will conservatively downgrade most answers to `insufficient_evidence` in production until/unless a Mongo-backed evidence tool is added to this surface — see Decisions Made above.

---
*Phase: 39-langchain-ai-integration*
*Completed: 2026-07-18*
