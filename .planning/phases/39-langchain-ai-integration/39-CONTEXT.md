# Phase 39: LangChain AI Integration - Context

**Gathered:** 2026-07-17
**Status:** Ready for planning
**Source:** Scope decisions via AskUserQuestion during /gsd-plan-phase 39 (post-research)

<domain>
## Phase Boundary

Migrate the platform's AI surfaces onto LangChain 1.x per 39-AI-SPEC.md. In scope: AI compliance auditor grounding + structured outputs, questionnaire auto-answer, narrative generation, and the Phase 38 assistant chat surface. Out of scope: legacy `/api/ai/chat` demo-tour/skill dispatcher, `agent_chat_endpoints.py` (human-to-human relay — no LLM).

</domain>

<decisions>
## Implementation Decisions

### Chat surface scope
- Migrate ONLY Phase 38's `/api/assistant/chat` (`ai_assistant_service.py`) onto LangChain `create_agent`. Legacy `/api/ai/chat` (demo-tour/skill dispatcher behind `ChatAssistant.tsx`) stays untouched this phase.

### Old code disposition
- Keep compatibility shims: `ai_auditor_service.py`, `compliance_narrative_service.py`, `questionnaire_answer_draft_service.py` keep their public functions/API contracts; internals swap to LangChain paths. No frontend or route changes. Deletion deferred to a later phase.

### Locked by 39-AI-SPEC.md (framework contract)
- LangChain pinned `langchain==1.3.14` + companion packages (Section 2)
- `create_agent` + `init_chat_model(model_provider="openai", base_url=9router)` with `.with_fallbacks([ollama])` (Section 3)
- tenant_id closed over server-side in tools — never a model-supplied argument
- Do NOT rewrap existing ChromaDB collection with langchain-chroma — wrap `rag_service.query` in `@tool` instead
- Async-only in FastAPI paths (`ainvoke`/`astream`)
- Citation-required Pydantic schemas (`AuditFinding` with `citations: min_length=1`)
- Phoenix self-hosted tracing + `openinference-instrumentation-langchain`; no LangSmith
- Eval fixtures under `backend/tests/eval_langchain/`; CI gate `pytest -m "eval and not llm"`

### Claude's Discretion
- Migration/wave ordering (research recommends a Wave-0 smoke test of 9router `tools`/`response_format` passthrough — genuinely untested)
- `agent_ai_decisions` schema reconciliation approach (research: incompatible shape; needs explicit decision in plan, not silent extension)
- Shim internals structure, new module layout (respect 500-line CLAUDE.md limit)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### AI design contract
- `.planning/phases/39-langchain-ai-integration/39-AI-SPEC.md` — framework decision, implementation patterns, guardrails, eval strategy (LOCKED)

### Research
- `.planning/phases/39-langchain-ai-integration/39-RESEARCH.md` — codebase AI call-path map, migration risks, PyPI verification, open questions

</canonical_refs>

<specifics>
## Specific Ideas

- Research flagged 9router tool-calling passthrough as LOW confidence — plan must front-load a live smoke test before any surface migration depends on it.
- Four hand-rolled JSON-extraction implementations collapse onto `response_format=Schema` — biggest structural win.
- `LangChainInstrumentor` must be added in `app_startup.py::init_agentic_tracing()` or new spans invisible.

</specifics>

<deferred>
## Deferred Ideas

- Legacy `/api/ai/chat` migration (explicitly out of scope this phase)
- Deleting replaced service internals (shims kept; removal in later phase)

</deferred>

---

*Phase: 39-langchain-ai-integration*
*Context gathered: 2026-07-17 via post-research scope decisions*
