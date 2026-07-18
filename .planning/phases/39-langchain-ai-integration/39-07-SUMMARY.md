---
phase: 39-langchain-ai-integration
plan: 07
subsystem: ai
tags: [langchain, langgraph, create_agent, chat, checkpointer, rag, guardrails, tenant-isolation]

# Dependency graph
requires:
  - phase: 39-langchain-ai-integration/39-04
    provides: build_model_for_tenant (per-tenant model factory), make_thread_id + checkpointer_lifespan (persistent tenant-prefixed memory), attach_span_attributes (tracing)
  - phase: 39-langchain-ai-integration/39-05
    provides: make_search_evidence (tenant-closed retrieval tool), CHAT_SYSTEM_PROMPT + PROMPT_VERSION, scan_input/scan_output/cross_tenant_output_scan (guardrails), log_ai_decision (decision log)
provides:
  - ai_orchestration/agents/chat.py — create_agent chat surface (ainvoke + astream) with tenant-scoped retrieval, persistent checkpointer memory, guardrails, provenance
  - ai_assistant_service.py rewritten as a thin shim preserving chat()'s {answer, sources} contract
  - 10 hermetic unit tests (test_chat_agent.py) covering agent + shim behavior
affects: [39-08-questionnaire, 39-09-narrative, 39-11-eval-code-dimensions, 39-12-eval-llm-dimensions]

tech-stack:
  added: []
  patterns:
    - "create_agent + tenant-closed @tool factory + checkpointer thread_id = f'{tenant}:{conversation}' (same shape as 39-06 auditor, applied to the free-text chat surface)"
    - "Direct RAG/live-findings fetch preserved alongside the agent's own search_evidence tool call, so `sources` stays deterministic/citable even on a turn the model never calls the tool"
    - "Chat is the one Phase 39 surface with NO structured response_format — free-text answer only, ainvoke for JSON endpoint / astream for future SSE endpoint"

key-files:
  created:
    - backend/ai_orchestration/agents/chat.py
    - backend/tests/test_chat_agent.py
  modified:
    - backend/ai_assistant_service.py
    - backend/tests/test_ai_assistant.py

key-decisions:
  - "chat.py preserves ai_assistant_service.chat()'s exact RAG + live-findings (failing controls, open high/critical risks) fusion via direct rag_service.query()/db queries, in addition to giving the agent its own search_evidence tool — guarantees deterministic {type,id,title,snippet} sources regardless of whether the model calls the tool mid-turn"
  - "Uses the real persistent checkpointer (ai_orchestration.memory.checkpointer_lifespan, defaulting to AsyncSqliteSaver) rather than InMemorySaver, since chat is the multi-turn conversational surface the 39-AI-SPEC explicitly calls out for real persistent memory (unlike 39-06 auditor's per-control InMemorySaver, which doesn't need cross-restart memory)"
  - "conversation_id defaults to 'default' when the caller (today's endpoint) doesn't supply one, so make_thread_id's non-empty requirement is always satisfied — thread_id is still always tenant-prefixed"
  - "astream_chat implemented per acceptance criteria but not wired into ai_assistant_endpoints.py this plan (39-CONTEXT.md scopes that re-point as a separate follow-up)"

requirements-completed: [AISPEC-39-S4, AISPEC-39-S4b, AISPEC-39-S6, AISPEC-39-S7, RESEARCH-Pat4]

duration: ~35min
completed: 2026-07-18
status: complete
---

# Phase 39 Plan 07: create_agent Chat Migration Summary

**Migrated `/api/assistant/chat` onto a `create_agent` built on the 39-04 model factory + 39-05 tenant-closed `search_evidence` tool, with persistent tenant-prefixed checkpointer memory replacing the old in-process demo-session anti-pattern, while preserving the exact `{answer, sources}` contract via a thin shim.**

## Performance

- **Duration:** ~35 min
- **Tasks:** 3
- **Files modified/created:** 4 (chat.py, ai_assistant_service.py, test_chat_agent.py, test_ai_assistant.py)

## Accomplishments

- `backend/ai_orchestration/agents/chat.py`: `chat()` (ainvoke, await path for the JSON endpoint) and `astream_chat()` (astream, generator path for a future SSE re-point) both build a per-tenant `create_agent` with the `search_evidence` tool, versioned `CHAT_SYSTEM_PROMPT`, and a real persistent checkpointer keyed on `make_thread_id(tenant_id, conversation_id)` — two tenants sharing a `conversation_id` never share memory.
- RAG + live-findings (failing controls last 30 days, open high/critical risks) fusion preserved verbatim in intent from the old `ai_assistant_service.chat()`, including both isolation layers (server-side `$or` filter inside `rag_service.query`, client-side skip of any chunk tagged with a foreign tenant id) — `sources` keeps its exact `{type, id, title, snippet}` shape.
- `scan_input` runs before the agent call; `scan_output` + `cross_tenant_output_scan` run after; any block downgrades to a safe `{answer: "...flagged...", sources: []}` response rather than surfacing an unsafe answer.
- `model_provenance` stamped from the final message's `response_metadata`; span attributes (`tenant_id`, `surface="chat"`, `PROMPT_VERSION`, `model_provenance`) attached on every turn; every answered/blocked/errored turn is logged via `log_ai_decision` (never blocks the response on a log failure).
- `ai_assistant_service.py` rewritten to a 55-line shim: `chat(query, tenant_id, history=None)` resolves `db` via `get_database()` and delegates to `agent_chat`, returning `{answer: <error>, sources: []}` on any exception rather than raising.
- 10 new hermetic tests in `test_chat_agent.py` (`-k agent` / `-k shim`), and the 5 pre-existing `test_ai_assistant.py` tests retargeted onto the new call graph (see Deviations) — all green, no live model/gateway/Chroma/sqlite calls.

## Task Commits

Each task was committed atomically:

1. **Task 1: create_agent chat with tenant-scoped retrieval + memory + guardrails** - `bd4a286` (feat)
2. **Task 2: ai_assistant_service.py compatibility shim** - `8d4bc77` (feat)
3. **Task 3: Chat agent + shim unit tests** - `b6f78e1` (test)

**Deviation fix commit:** `16ea4c7` (fix) — see Deviations below.

## Files Created/Modified

- `backend/ai_orchestration/agents/chat.py` (372 lines) - `chat()`/`astream_chat()`: create_agent + tenant-closed retrieval + checkpointer memory + guardrails + provenance + decision log
- `backend/ai_assistant_service.py` (55 lines, was 152) - thin shim delegating to `ai_orchestration.agents.chat.chat`
- `backend/tests/test_chat_agent.py` (280 lines, new) - 10 hermetic tests, `-k agent` (7) / `-k shim` (3)
- `backend/tests/test_ai_assistant.py` (242 lines, was 189) - 5 pre-existing tests retargeted onto the new mocking boundary (see Deviations)

## Decisions Made

- Kept the direct RAG/live-findings fetch (rather than relying solely on the agent's own tool call) so the returned `sources` list is deterministic and testable independent of whether/how the model chooses to invoke `search_evidence` mid-turn — this is additive, not a replacement: the agent still has the tool available for further targeted lookups.
- Used the real persistent `AsyncSqliteSaver`-backed checkpointer (via `checkpointer_lifespan()`) for chat's multi-turn memory, distinct from 39-06 auditor's per-control `InMemorySaver()` — chat is the surface 39-AI-SPEC explicitly calls out as needing memory that survives a restart.
- `conversation_id` defaults to `"default"` when absent (today's endpoint doesn't send one) so `make_thread_id`'s non-empty-id invariant always holds while still being fully tenant-prefixed; a future endpoint re-point to real per-conversation ids is a drop-in, no chat.py change needed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Retargeted `test_ai_assistant.py`'s mocking layer onto the new chat-agent call graph**
- **Found during:** Task 2 verification (running the plan's own phase-level `<verification>` command `pytest backend/tests/test_ai_assistant.py -q`)
- **Issue:** The pre-existing 5 tests in `test_ai_assistant.py` patched `ai_assistant_service.rag_service` / `ai_assistant_service.ai_service` — module attributes that no longer exist once `chat()` became a shim delegating to `ai_orchestration.agents.chat`. All 5 tests failed with `AttributeError: ... does not have the attribute 'rag_service'` immediately after Task 2's rewrite (this file is not in the plan's declared `<files>` list for either task, but the plan's own phase-level verification explicitly requires `pytest backend/tests/test_ai_assistant.py -q` to still exit 0 with "contract preserved").
- **Fix:** Retargeted the same 5 tests' patches to the new boundary (`ai_orchestration.agents.chat.rag_service`, `.build_model_for_tenant`, `.create_agent`, `.checkpointer_lifespan`, plus `ai_assistant_service.get_database`), added the `guardrail_service.scan_and_log` stub autouse fixture the new code path requires (surfaced as a second failure — a real, unmocked `get_database()` call inside the guardrail scan — once the first fix was applied), and adjusted the tenant-isolation assertion to check the content forwarded to `agent.ainvoke` instead of `ai_service.generate_text`. Test names, fixture data, and all behavioral assertions (sources present/absent by id, tenant isolation, endpoint 200 + shape, empty-query short-circuit, SSE frame contract) are unchanged.
- **Files modified:** `backend/tests/test_ai_assistant.py`
- **Verification:** `pytest backend/tests/test_ai_assistant.py -q` → 5 passed; full `pytest tests/ -q --ignore=tests/test_rebac.py` → 1073 passed / 23 skipped / 2 failed (both pre-existing, unrelated — see Issues Encountered below).
- **Committed in:** `16ea4c7` (separate commit, not folded into Task 2, since it touches a file outside that task's declared scope)

---

**Total deviations:** 1 auto-fixed (1 blocking — required to satisfy the plan's own phase-level verification)
**Impact on plan:** No scope creep beyond what the plan's own `<verification>` block already demanded; the file's behavioral contract (not just its literal bytes) is what "contract preserved" means once the internals genuinely changed from a hand-rolled prompt+`ai_service.generate_text` call to a `create_agent` delegation.

## Issues Encountered

- Two known pre-existing failures reproduce identically and are unrelated to this plan's 4 files: `test_e2e_integration.py::test_golden_path_evidence_to_remediation` ("no systemGenerated=True evidence pushed") and `test_rust_heartbeat_parity.py::test_rust02_and_rust03_db_calls` (missing `agent_type` in a `$push.evidence` array) — both called out in the executor briefing as out of scope; not fixed.
- The docstring in `chat.py` initially contained the literal substring `` `.invoke(` `` while explaining the async-only rule, which self-tripped the plan's own `grep -Ec '\.invoke\(|asyncio\.run\('` acceptance-criteria gate (the same self-tripping literal-string pitfall 39-05's SUMMARY documented for its own docstrings) — caught before commit and rephrased without changing the meaning.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `agents/chat.py` establishes the same `create_agent` + tenant-closed-tool + checkpointer + guardrails + provenance + decision-log pattern 39-08 (questionnaire) and 39-09 (narrative) will follow, plus the first working example of the free-text (no `response_format`) variant of that pattern for any future non-structured surface.
- `astream_chat()` is built and unit-tested but not yet consumed by `ai_assistant_endpoints.py::_stream_answer` — re-pointing the SSE endpoint at true token-level streaming (instead of the current word-split-the-full-answer simulation) is an explicit, scoped-out follow-up per 39-CONTEXT.md, not a blocker for 39-08/39-09.
- No blockers for 39-08/39-09.

---
*Phase: 39-langchain-ai-integration*
*Completed: 2026-07-18*
