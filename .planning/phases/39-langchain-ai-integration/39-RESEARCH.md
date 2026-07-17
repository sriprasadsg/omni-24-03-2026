# Phase 39: LangChain AI Integration - Research

**Researched:** 2026-07-17
**Domain:** LangChain 1.x migration of existing multi-surface AI stack (FastAPI/async, MongoDB, ChromaDB) — codebase-side research. Framework selection, quick reference, best practices, eval strategy, and guardrails are already locked in `39-AI-SPEC.md`; this document maps AI-SPEC's prescriptions onto the actual current code.
**Confidence:** HIGH (codebase claims) / MEDIUM (LangChain-specific claims — cross-referenced against AI-SPEC's own Context7/official-docs citations, not re-fetched here)

## Summary

This phase's hardest problem is not LangChain — it's that the phase brief's own map of "existing AI surfaces" is wrong in one load-bearing place, and the actual codebase has **two independent, non-RAG-grounded chat backends and one auditor with zero citation infrastructure**, none of which match the AI-SPEC's assumed starting shapes closely enough to "migrate" — most of Section 5's evaluation dimensions (citation validation, structured `AuditFinding`, framework-fidelity checks) do not exist today and must be built, not lifted.

Concretely: `agent_chat_endpoints.py` (named in the phase brief as "the chat assistant") is **not an AI surface at all** — it's a human-to-human admin↔endpoint-agent messaging relay with no LLM call anywhere in the file. The actual AI chat assistant used by `ChatAssistant.tsx` is `/api/ai/chat` (`ai_endpoints.py` → `ai_service.chat()`), a stateful, hand-rolled demo-tour/skill-dispatch chatbot with **no RAG grounding and no citations**. A second, separate, RAG-grounded chat surface already exists from Phase 38: `/api/assistant/chat` (`ai_assistant_endpoints.py` → `ai_assistant_service.chat()`), which already does tenant-scoped RAG + live-findings retrieval + source citations — this is the surface structurally closest to what the AI-SPEC's `create_agent` pattern wants to become, not `ai_endpoints.py`. The compliance auditor (`ai_auditor_service.py`) currently produces a raw two-line `VERDICT:`/`REASONING:` text parse with **no citations, no control-ID validation, and no Pydantic schema** — every citation/traceability guardrail in AI-SPEC Section 5/6 is new work here, not a wrap-and-migrate.

**Primary recommendation:** Migrate in this order — (1) auditor (`ai_auditor_service.py` → `AuditFinding` schema + citation validator, highest-value/highest-risk, currently has zero grounding), (2) narrative generation (`compliance_narrative_service.py`, already has the closest-matching Pydantic-validated-output pattern to reuse), (3) questionnaire RAG (`questionnaire_answer_draft_service.py`, already has grounding + a working human-approval gate to preserve as-is), (4) chat — but retarget the "chat assistant" migration onto **Phase 38's `ai_assistant_service.py`/`/api/assistant/chat`**, not `agent_chat_endpoints.py`. Do not touch `agent_chat_endpoints.py` in this phase; it is out of scope by construction (no LLM call exists in it to migrate). Treat `/api/ai/chat` (`ai_endpoints.py`) as a UI-facing legacy surface that the plan should either explicitly descope with a stated reason, or fold into the migrated `ai_assistant_service` agent as a second consumer — this is a real open scope question for the planner/user, not a research gap that can be silently resolved.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Compliance audit evaluation (auditor agent) | API / Backend | Database (Mongo `asset_compliance`, `control_evidence`) | Background task in `ai_auditor_endpoints.py`; findings persist to Mongo, not the agent's own memory |
| Questionnaire RAG auto-answer | API / Backend | Database / Storage (ChromaDB `omni-agent-knowledge`) | Retrieval + generation + Pydantic validation all server-side; frontend only renders/approves |
| Chat assistant (`ai_assistant_service`, Phase 38) | API / Backend | Database (Mongo `compliance_evidence`, `risks`) + ChromaDB | RAG + live-findings fusion happens entirely in the service layer before any LLM call |
| Chat assistant (legacy `/api/ai/chat`, `ai_service.chat`) | API / Backend | — (no retrieval tier) | Stateful demo/skill dispatcher; no grounding tier at all today |
| Narrative generation (PDF reports) | API / Backend | Database (Mongo `compliance_frameworks`, `asset_compliance`) | Invoked synchronously inside `_generate_report`/`enrich_report_data`, output embedded in a PDF, not returned to a user turn |
| Conversation memory (LangGraph checkpointer) | API / Backend | Database / Storage (SQLite under `data/`, matching existing ChromaDB-on-disk convention) | New in this phase — no existing analog; must not live in-process only (Pitfall 5) |
| Tracing (Phoenix/OTLP spans) | API / Backend | — | `app_startup.py` process-local instrumentation, self-hosted, never leaves the box |
| Frontend chat UI (`ChatAssistant.tsx`) | Browser / Client | Frontend Server (SSR: none — this is a Vite SPA) | Renders SSE stream; no business logic, no tenant scoping decisions made here |

## Package Legitimacy Audit

All 9 packages from AI-SPEC Section 2/3 were checked against PyPI directly (`pip index versions`) and via the `package-legitimacy check` seam.

| Package | Registry | Published (pinned version) | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|------------------------------|-----------|--------------|---------|--------------|
| `langchain==1.3.14` | PyPI | 2026-07-16 | n/a (checker has no PyPI download-count source) | `docs.langchain.com` / `github.com/langchain-ai/langchain` | SUS (`too-new`, `unknown-downloads`) | Approved — see note |
| `langchain-core==1.4.9` | PyPI | 2026-07-08 | n/a | `github.com/langchain-ai/langchain` | SUS (`too-new`, `unknown-downloads`) | Approved — see note |
| `langgraph==1.2.9` | PyPI | 2026-07-10 | n/a | `github.com/langchain-ai/langgraph` | SUS (`too-new`, `unknown-downloads`) | Approved — see note |
| `langchain-openai==1.3.5` | PyPI | 2026-07-10 | n/a | `docs.langchain.com/.../openai` | SUS (`too-new`, `unknown-downloads`) | Approved — see note |
| `langchain-anthropic==1.4.8` | PyPI | 2026-06-26 | n/a | `docs.langchain.com/.../anthropic` | SUS (`too-new`, `unknown-downloads`) | Approved — see note |
| `langchain-ollama==1.1.0` | PyPI | 2026-04-07 | n/a | `docs.langchain.com/.../ollama` | SUS (`unknown-downloads`) | Approved — see note |
| `langchain-chroma==1.1.0` | PyPI | 2025-12-12 | n/a | `github.com/langchain-ai/langchain/.../chroma` | SUS (`unknown-downloads`) | Not needed this phase (Pitfall 2 — do not install unless the Chroma re-embed migration is separately scoped) |
| `openinference-instrumentation-langchain==0.1.67` | PyPI | 2026-07-01 | n/a | `github.com/Arize-ai/openinference` | SUS (`too-new`, `unknown-downloads`) | Approved — see note |
| `langgraph-checkpoint-sqlite==3.1.0` | PyPI | 2026-05-12 | n/a | `github.com/langchain-ai/langgraph/.../checkpoint-sqlite` | SUS (`unknown-downloads`) | Approved — see note; needed for the prod checkpointer (Pitfall 5), not in AI-SPEC's pinned list — **add explicitly**, version confirmed on PyPI |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** all 9 above, uniformly, for the same two checker reasons — `too-new` (the automated checker flags any package version published within its recency window, and every one of these is a routine point release of an actively-maintained package published within the last few weeks) and `unknown-downloads` (the legitimacy checker has no PyPI download-count data source at all, unlike its npm equivalent — this reason will fire on literally every PyPI package checked through this seam and carries no signal). **Note for planner:** these are not indicators of a hallucinated/slopsquatted package — `langchain`/`langgraph`/`langchain-anthropic`/etc. are the real, actively-maintained LangChain-AI-org packages (confirmed via `docs.langchain.com` and `github.com/langchain-ai` source repos returned by the checker itself, and every version number matches AI-SPEC's own pins fetched from `pypi.org/pypi/langchain/json` on the same date as this research). Per the package-legitimacy protocol, the planner must still gate each `pip install` behind a `checkpoint:human-verify` task since the automated verdict is SUS — but the verification is a rubber-stamp confirmation of already-corroborated facts, not exploratory due diligence. `[ASSUMED]` tag applies to `langchain-chroma` only because it is out of scope for this phase per Pitfall 2 and should not appear in any install command the planner writes.

**Runtime compatibility check (this session, `backend/venv`):** `pydantic==2.13.4` and `fastapi==0.136.3` are already installed and satisfy LangChain 1.x's `pydantic>=2` requirement — no conflict. `chromadb==1.5.9` is installed but **irrelevant to this phase** per Pitfall 2 (rag_service.py stays wrapped, not rewrapped). `anthropic==0.107.1` SDK is installed and used directly by `AnthropicProvider`/`app_startup.py`'s `AnthropicInstrumentor` — LangChain's Anthropic/OpenAI integration packages do not need to replace this; they are additive, used only inside `ai_orchestration/`.

## Architecture Patterns

### System Architecture Diagram

```
                    ┌─────────────────────────────────────────────────────────┐
                    │  Frontend (Vite SPA)                                    │
                    │  ChatAssistant.tsx ──POST /api/ai/chat(/stream)──┐       │
                    │  (Phase 38 UI, if any, ──POST /api/assistant/*)  │       │
                    └───────────────────────────────────────────────┼─┼───────┘
                                                                     │ │
                          ┌──────────────────────────────────────────┘ │
                          │                    ┌────────────────────────┘
                          ▼                    ▼
              ┌───────────────────┐  ┌──────────────────────────┐
              │ ai_endpoints.py    │  │ ai_assistant_endpoints.py │
              │ (legacy chat,      │  │ (Phase 38 RAG chat,       │
              │  demo/skill logic) │  │  ALREADY grounded)        │
              └─────────┬──────────┘  └────────────┬──────────────┘
                        │                          │
                        ▼                          ▼
              ┌───────────────────┐    ┌──────────────────────────┐
              │ ai_service.py      │    │ ai_assistant_service.py   │
              │ IncidentAnalyzer  │◄───┤  chat(query, tenant, hist)│
              │ .generate_text()  │    │  - rag_service.query()    │
              │  - guardrails     │    │  - Mongo live findings    │
              │  - retry/backoff  │    │  - builds prompt          │
              │  - ai_breaker     │    │  - calls ai_service        │
              │  - provider cache │    └──────────────────────────┘
              │    (per tenant)   │
              └─────────┬──────────┘
                        │  (provider selected: 9router / Ollama / Anthropic / Gemini / Mock)
                        ▼
              ┌───────────────────────────────┐
              │ ai_providers.py                │
              │ OpenAICompatProvider (9router) │──HTTP──► 9router gateway ──► Anthropic
              │ OllamaProvider (fallback)      │──HTTP──► local Ollama
              └───────────────────────────────┘

  Parallel surfaces reusing the SAME ai_service + rag_service, independently:

  ai_auditor_endpoints.py ──background_task──► ai_auditor_service.get_auditor()
        │                                              │
        │ reads asset_compliance evidence              │ raw VERDICT/REASONING text parse
        ▼                                              │ (NO citations, NO schema today)
  db.asset_compliance.update_one(ai_evaluation, reason, remediation)

  questionnaire_answer_draft_service.py ──rag_service.query()──► ChromaDB (tenant-scoped)
        │                                     │
        │ builds prompt, calls ai_service      │
        ▼                                     ▼
  AnswerDraft (Pydantic) ──insert──► questionnaire_answer_drafts (status=pending_review)
        │
        ▼
  questionnaire_answer_review_endpoints.py ── approve/reject/submit (RAG-02 gate, EXISTING)

  compliance_narrative_service.py ──enrich_report_data()──► ai_service.generate_text()
        │
        ▼
  NarrativeOutput (Pydantic, word-budget validated) ──embedded──► PDF report (reportlab)

  app_startup.py::init_agentic_tracing() ──OTLP──► Phoenix (localhost:6006), Anthropic spans ONLY today
```

### Recommended Project Structure

Matches AI-SPEC Section 3 verbatim (`backend/ai_orchestration/…`) — confirmed compatible with the actual codebase's existing per-file organization convention (one service module per AI surface, endpoints thin, `router_registry.py` central registration). No structural objection found. One addition based on this session's findings:

```
backend/
├── ai_orchestration/
│   ├── __init__.py
│   ├── models.py                # init_chat_model factories — read same system_settings
│   │                             # shape IncidentAnalyzer.get_provider_for_tenant reads
│   │                             # (type: "llm", tenantId: ...) — see Pitfall A below
│   ├── agents/
│   │   ├── auditor.py           # replaces ai_auditor_service.LocalAIAuditor.evaluate_evidence
│   │   ├── chat.py               # wraps ai_assistant_service.chat() logic — NOT agent_chat_endpoints.py
│   │   ├── questionnaire.py     # replaces questionnaire_answer_draft_service.draft_answer_for_question
│   │   └── narrative.py         # NEW — AI-SPEC's structure omits this; narrative gen is its own surface
│   ├── tools/
│   │   ├── retrieval.py         # tenant-scoped rag_service.query() @tool wrapper
│   │   └── evidence.py          # get_control_status / list_asset_evidence wrappers over Mongo
│   ├── schemas.py                # AuditFinding, CitedAnswer, NarrativeOutput-equivalent, Citation
│   ├── prompts.py                 # PROMPT_VERSION constants
│   ├── memory.py                  # AsyncSqliteSaver setup, thread_id policy
│   └── tracing.py                # NEW — LangChainInstrumentor wiring, called from app_startup.py
├── rag_service.py                # UNCHANGED — wrapped by tools/retrieval.py, not rewrapped
├── ai_service.py                 # UNCHANGED — its provider cache/circuit-breaker/guardrail plumbing
│                                  # stays the source of truth for tenant provider settings; models.py
│                                  # reads the SAME system_settings documents, does not duplicate them
├── ai_auditor_service.py         # becomes a thin compatibility shim or is retired once auditor.py ships
├── compliance_narrative_service.py  # becomes a thin shim calling agents/narrative.py, or retired
└── questionnaire_answer_draft_service.py  # becomes a thin shim calling agents/questionnaire.py
```

### Pattern 1: Reuse the existing per-tenant provider settings shape, don't invent a new one
**What:** `ai_orchestration/models.py`'s `build_model_for_tenant` (AI-SPEC Section 4) must read from `db.system_settings.find_one({"type": "llm", "tenantId": tenant_id})` — the exact query `IncidentAnalyzer.get_provider_for_tenant` already runs — and must call `ai_service.invalidate_tenant_provider(tenant_id)`'s cache-eviction pattern when settings change, not a separate cache with its own invalidation path.
**When to use:** Every `init_chat_model(...)` call site in the new orchestration layer.
**Example:**
```python
# backend/ai_orchestration/models.py — settings shape confirmed from ai_service.py:80
raw = db._db if hasattr(db, "_db") else db
settings = await raw.system_settings.find_one({"type": "llm", "tenantId": tenant_id})
# settings.get("provider") is one of: "9router"/"OpenAI-Compatible"/"openai_compat"/"router",
# "Ollama (Local)"/"Local"/"ollama", "Anthropic Claude", "Gemini" — see ai_service.py:20-49
```

### Pattern 2: Tool-wrap `rag_service.query`, never rewrap ChromaDB
**What:** confirmed correct in AI-SPEC (Pitfall 2). `rag_service.py`'s `collection.add(...)` relies on Chroma's *implicit default* embedding function (no explicit `embedding_function=` passed to `get_or_create_collection`) — this session confirmed that by reading the file directly (`rag_service.py:23`). Any LangChain `Chroma(...)` wrapper requires an explicit `embedding_function=` argument; passing anything other than exactly Chroma's built-in default (which LangChain does not replicate as a first-class option — it expects a `langchain_core.embeddings.Embeddings` object) changes every existing vector's comparability silently.
**When to use:** Always, in this phase. `langchain-chroma` stays uninstalled.

### Pattern 3: The auditor's control-ID/citation validator has no registry to check against yet — it must query `compliance_frameworks`, not a hardcoded map
**What:** AI-SPEC's citation validator ("look up `control_id` in the framework map") should resolve against `db.compliance_frameworks.find_one({"id": framework_id, ...}).controls[].id` — this is the exact collection `ai_auditor_endpoints.py:31` already queries (`controls_map = {c["id"]: c for c in framework.get("controls", [])}`). There is no separate `COMPLIANCE_CHECK_MAPPINGS`-style static registry for *frameworks themselves* (that constant maps SaaS/cloud checks to controls, a different concept — confirmed by requirement SAAS-02/PROV-03 usage, not framework control IDs). Citations must resolve against `control_evidence`/`asset_compliance` evidence records, which is the collection the auditor already reads (`db.asset_compliance.find({"controlId": {"$in": ...}})`).
**When to use:** Building the code-based traceability guardrail (AI-SPEC Section 5, dimension 1).

### Pattern 4: Tenant-scoped RAG isolation is already implemented and tested — reuse verbatim
**What:** `rag_service.query(query_text, n_results, tenant_id)` already applies `{"$or": [{"tenantId": tenant_id}, {"tenantId": "global"}]}` (Phase 30-01 fix, confirmed present in the file this session — STATE.md's claim of a real fix, not a stale claim, is verified). `ai_assistant_service.chat()` adds a second belt-and-braces client-side filter on top. The new `@tool search_evidence` wrapper in AI-SPEC's entry-point pattern should call this exact function signature unchanged.
**When to use:** Every retrieval tool in `ai_orchestration/tools/retrieval.py`.

### Anti-Patterns to Avoid
- **Treating `agent_chat_endpoints.py` as an AI surface:** it is a real-time human messaging relay (admin ↔ endpoint agent via Socket.IO + polling), with zero LLM calls. Migrating it to LangChain would be migrating nothing — there is nothing to migrate. If the phase's actual intent was the *frontend* `ChatAssistant.tsx` component, that component calls `/api/ai/chat`, not anything in `agent_chat_endpoints.py`.
- **Duplicating the provider-settings cache:** `ai_orchestration/models.py` must not maintain its own `_tenant_providers`-equivalent cache independent of `ai_service`'s — two caches invalidated by two different code paths is how a tenant's provider-switch silently fails to take effect on one surface but not another.
- **Wrapping `ai_service.generate_text()` inside a LangChain tool/model call:** `generate_text` already does guardrail scan + retry + circuit breaker + provider selection. If a `create_agent`'s model IS `init_chat_model(...)` talking directly to the 9router, do not also route it through `ai_service.generate_text` — that double-wraps guardrails and retries in two different ways with two different backoff policies. Guardrails should be pre/post hooks around `agent.ainvoke()` directly (as AI-SPEC Section 4 already specifies), not routed through the old generate_text path.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Provider-agnostic model client (9router + Ollama + Anthropic + Gemini) | A fifth bespoke provider abstraction alongside `ai_providers.py`'s existing 4 | `init_chat_model` + `.with_fallbacks([...])` (already locked in AI-SPEC) | This is the entire reason LangChain was selected; a second parallel abstraction defeats the point and doubles maintenance |
| Structured-output parsing/repair for LLM JSON | Regex/`json.loads` + manual retry (the pattern currently used in `questionnaire_answer_draft_service.py`, `compliance_narrative_service.py`, `ai_endpoints.py::analyze_impact`, `ai_endpoints.py::ai_threat_hunt` — 4 independent hand-rolled JSON-extraction implementations found this session) | `create_agent(response_format=Schema)` / `ToolStrategy` | Every hand-rolled variant found today has a slightly different bug surface (e.g. `analyze_impact`'s regex `\{[\s\S]+\}` is greedy and will over-match on nested braces in a finding's `metadata`); one framework-managed retry loop replaces four bespoke ones |
| Conversation memory / multi-turn state | A new Mongo collection + manual truncation (as `ai_service.py`'s `demo_sessions` dict already does, in-process only, not persisted) | LangGraph checkpointer (`AsyncSqliteSaver` prod, `InMemorySaver` dev) | `demo_sessions` is already a real production bug today — an in-process dict that vanishes on restart/multi-worker deploy; don't recreate that pattern in the new layer |
| Citation/evidence-ID validation | A per-surface ad-hoc string check | One shared `ai_orchestration/schemas.py` `Citation` model + one shared post-generation validator function called from every surface (auditor, questionnaire, chat) | AI-SPEC's Section 5/6 dimensions apply identically across 3 surfaces; one validator, three call sites |

**Key insight:** This codebase already has 4 independent hand-rolled "extract JSON from LLM text, hope it parses" implementations across `ai_endpoints.py`, `compliance_narrative_service.py`, `questionnaire_answer_draft_service.py`, and `ai_auditor_service.py`'s line-based VERDICT/REASONING parser. Every one is a slightly different bug. The single biggest win in this phase, independent of the RAG/tenant/guardrail concerns, is collapsing all four onto one `response_format=Schema` mechanism.

## Common Pitfalls

### Pitfall A: Two different "chat assistant" surfaces will collide if not explicitly scoped
**What goes wrong:** The plan migrates `ai_assistant_service.py` (Phase 38, already RAG-grounded) to LangChain, but the frontend (`ChatAssistant.tsx`) keeps calling the un-migrated `/api/ai/chat` (`ai_service.chat()`), so the "migration" ships with zero visible user-facing effect — no LangChain code path is ever exercised by a real user.
**Why it happens:** The phase brief names `agent_chat_endpoints.py`/`ChatAssistant.tsx` as the chat surface; neither the file nor the component call chain (`ChatAssistant.tsx` → `streamChatAssistantResponse` → `/api/ai` → `ai_endpoints.py` → `ai_service.chat_stream`) touches `ai_assistant_service.py` at all. They are two unrelated backends serving two different frontend surfaces (this session found no frontend consumer of `/api/assistant/chat` — it may be unwired, or wired in a component not grepped this session).
**How to avoid:** The plan must state explicitly, as a Wave-1 decision, whether: (a) `ChatAssistant.tsx` gets re-pointed at a migrated `/api/assistant/chat`-equivalent (real user-facing change, needs frontend task + UI-SPEC consideration), or (b) `/api/ai/chat`'s `ai_service.chat()` itself gets rebuilt as a `create_agent` (loses the demo-tour/skill-dispatch behavior unless explicitly ported), or (c) only `ai_assistant_service.py` migrates and `/api/ai/chat` is explicitly left alone this phase with a documented reason. Silence on this in the plan means "migrate the chat assistant" is unverifiable at goal-check time.
**Warning signs:** A plan verification step that greps for `create_agent` in `ai_assistant_service.py` but never checks whether `ChatAssistant.tsx`'s network calls changed.

### Pitfall B: `tenant_context` ContextVar cleanup is a known, still-open gap (SEC-03)
**What goes wrong:** `tenant_context.set_tenant_id(tenant_id)` (used today in `compliance_narrative_service.enrich_report_data` and `questionnaire_answer_draft_service.draft_answer_for_question`) is a bare `ContextVar`, and SEC-03 ("ContextVar cleanup on exception paths") is still unchecked/Planned in `REQUIREMENTS.md`. LangGraph's `create_agent` runs tool calls inside its own graph execution, potentially on a different asyncio Task than the one that called `set_tenant_id` at the request boundary — if a tool closure captures `tenant_id` directly (as AI-SPEC's own entry-point pattern correctly does via a Python closure argument, NOT via `get_tenant_id()`), this specific risk is avoided by construction. But any code in the new `ai_orchestration/` layer that reaches for `tenant_context.get_tenant_id()` instead of using the closed-over parameter reintroduces the exact SEC-03 leak class this phase's own Critical Failure Mode #1 is trying to prevent.
**Why it happens:** `get_tenant_id()` is the path of least resistance — it's already imported everywhere else in the codebase (`compliance_narrative_service.py`, `questionnaire_answer_draft_service.py` both use it) — but those call sites are synchronous linear execution, not a multi-step agent loop with tool calls potentially scheduled across tasks.
**How to avoid:** Every `@tool` closure in `ai_orchestration/tools/` must take `tenant_id` as a captured factory-function argument (exactly as AI-SPEC's `build_audit_agent(tenant_id)` pattern shows), never call `get_tenant_id()` from inside a tool body. Code-review rule, same class as the existing `\.invoke\(|asyncio\.run\(` grep-reject rule in AI-SPEC Section 4b.
**Warning signs:** `grep -rn "get_tenant_id()" backend/ai_orchestration/` returning any hit inside a `@tool`-decorated function.

### Pitfall C: Phoenix tracing today only instruments the raw Anthropic SDK — LangChain calls are invisible until explicitly wired
**What goes wrong:** `app_startup.py::init_agentic_tracing()` calls `AnthropicInstrumentor().instrument()` only. When the 9router path runs through `langchain_openai`'s OpenAI-compatible client (not the raw `anthropic` SDK), and when Ollama runs through `langchain_ollama`, none of those calls produce spans under the current instrumentation — the AI-SPEC's entire eval/monitoring section (Section 5/7) assumes traces exist for every surface, but today they exist for zero LangChain-mediated calls.
**Why it happens:** `AnthropicInstrumentor` patches the `anthropic` Python package's client classes specifically; it does not patch `langchain_anthropic`/`langchain_openai`'s internal HTTP clients.
**How to avoid:** Add `LangChainInstrumentor().instrument(tracer_provider=provider)` inside `init_agentic_tracing()` (or a new sibling function called at the same startup point) exactly as AI-SPEC Section 5 "Setup" specifies — this is a real code change to `app_startup.py`, not merely a pip install.
**Warning signs:** Phoenix UI showing zero spans for `create_agent`/tool-call activity after the migration ships, despite `arize-phoenix` being installed and `PHOENIX_OTLP_ENDPOINT` reachable.

### Pitfall D: `agent_ai_decisions` is a different subsystem's audit log, not a ready-made sink for this phase
**What goes wrong:** AI-SPEC Section 1b says the new LangChain surfaces' traces should feed `agent_ai_decisions` "the pair is what makes AI findings defensible" — but `agent_ai_decisions` today is written exclusively by `agentic_service.py` (Phase 12's endpoint-agent capability-selection loop: reasoning chain → selected tool → dispatched instruction), a structurally different decision shape (agent picks a *security capability tool to run on an endpoint*) than an audit finding or a chat answer. Assuming this collection is a drop-in sink for Phase 39's decisions without a schema reconciliation is a planning trap.
**Why it happens:** Both are "AI decision audit logs" in prose, but the document shapes (`task_id`, `selected_tool`, endpoint-agent context vs. `control_id`, `citations`, `surface`) don't overlap; AI-SPEC assumes extension where none of the write paths currently exist.
**How to avoid:** Either (a) write Phase 39's decisions into `agent_ai_decisions` with a new, explicitly-designed document shape (add a `surface` discriminator field: `"auditor"|"chat"|"questionnaire"|"narrative"` vs. the existing implicit `"agentic_task"` shape) and confirm no existing reader (`agentic_tasks_endpoints.py`'s `GET` routes) breaks on the new shape, or (b) create a new collection and note the AI-SPEC's audit-log unification claim as an open question for the user/planner rather than an established fact. This is a genuine architectural decision, not a research gap resolvable by more reading.
**Warning signs:** `agentic_tasks_endpoints.py`'s decision-list endpoints returning malformed/partial rows once Phase 39 documents start appearing in the same collection.

### Pitfall E: No pytest markers registered yet — AI-SPEC's `-m "eval and not llm"` commands will silently no-op
**What goes wrong:** AI-SPEC Section 5's CI/CD commands (`pytest backend/tests/eval_langchain/ -m "eval and not llm"`) assume `eval`/`llm` pytest markers exist. This session confirmed: no `pytest.ini`/`pyproject.toml`/`setup.cfg` marker registration exists anywhere in `backend/`, and `backend/tests/eval_langchain/` does not exist yet.
**Why it happens:** Markers are new to this phase; nothing currently registers them, so pytest will emit `PytestUnknownMarkWarning` and (with no `--strict-markers` set anywhere found) still run everything under `-m` filters based on ad-hoc string matches — meaning a typo'd marker name fails silently (0 tests selected, exit code 0) rather than erroring.
**How to avoid:** Wave 0 must add a `[pytest]` `markers =` section (or `pyproject.toml` equivalent) registering `eval` and `llm`, and the plan's verification step should assert `pytest --collect-only -m eval` selects a non-zero test count, not just that the command exits 0.
**Warning signs:** CI showing 0 tests run under the eval marker with a green exit code.

## Runtime State Inventory

> Not a rename/refactor/migration phase in the CLAUDE.md sense (no string renames, no cross-system re-registration) — this is new-code-alongside-old, with old code paths retired incrementally. The 5-category inventory below is included because AI-SPEC's own framing ("migrate...onto LangChain") triggers the same "what still points at the old thing after the code changes" question.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `questionnaire_answer_drafts` (Mongo) already has a `pending_review`/`approved`/`submitted` state machine (Phase 30) — unaffected by a LangChain-based *generation* rewrite as long as the document shape (`answerText`, `confidence`, `sourceEvidenceIds`, `status`) is preserved. ChromaDB `omni-agent-knowledge` collection (Phase 16/30) — unaffected; not re-embedded (Pitfall 2). No renamed collections in this phase. | Code edit only (schema-shape preservation, not a data migration) — confirm new `agents/questionnaire.py` writes the identical Mongo document shape the frontend (`InboundQuestionnaireDashboard`) and `questionnaire_answer_review_endpoints.py` already read. |
| Live service config | None found — no n8n/external SaaS config carries "old" AI-surface identifiers that this phase renames. The 9router gateway URL/key (`AI_ROUTER_URL`/`AI_ROUTER_KEY` env vars, or per-tenant `system_settings` documents) is read, not renamed. | None. |
| OS-registered state | None — this phase is backend Python service code + one new SQLite checkpointer file under `data/`; no OS task-scheduler/pm2/systemd entries reference any AI-surface name being changed. | None. |
| Secrets/env vars | `AI_ROUTER_URL`, `AI_ROUTER_KEY`, `AI_ROUTER_MODEL`, `OLLAMA_URL`, `OLLAMA_MODEL`, `PHOENIX_OTLP_ENDPOINT` — all read unchanged by the new `ai_orchestration/models.py` (same env var names `OpenAICompatProvider.configure` already reads). No key renames. | None — code reads existing env vars, no rotation needed. |
| Build artifacts / installed packages | New SQLite file(s) under `data/` for `AsyncSqliteSaver` — additive, not a stale artifact from a rename. `backend/venv` gains 9 new pip packages (Package Legitimacy Audit above) — this is a fresh install, not a stale-artifact cleanup. | Install step only; no reinstall-of-existing-package concern. |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python venv (`backend/venv`) | All backend code/tests | ✓ | pydantic 2.13.4, fastapi 0.136.3, chromadb 1.5.9, anthropic 0.107.1 confirmed installed | — |
| `langchain` + 8 sibling packages | This entire phase | ✗ (not yet installed) | pinned versions all confirmed to exist on PyPI (see audit above) | None viable — this is the phase's core dependency; must install |
| 9router gateway | Primary model route (all surfaces) | Not verified reachable this session (no `AI_ROUTER_URL` probe run — requires live gateway process, out of scope for a static research pass) | — | Ollama fallback path (`with_fallbacks`) is itself the documented fallback; if 9router is down at eval time, tests should exercise the fallback path explicitly rather than skip |
| Ollama (local) | Offline/air-gapped fallback route | Not verified reachable this session | — | If unavailable in dev, `InMemorySaver`/mocked model tests can proceed without a live Ollama; production deploy must confirm before enabling per-tenant `Ollama (Local)` provider config |
| Arize Phoenix (self-hosted, `:6006`/`:4318`) | Tracing (Section 5/7) | `arize-phoenix` already pinned in `backend/requirements.txt` (not just `-eval`); `app_startup.py::init_agentic_tracing` already wired for Anthropic spans | installed per requirements.txt | If Phoenix process isn't running, `init_agentic_tracing`'s existing try/except already degrades gracefully (logs warning, doesn't block startup) — same pattern must extend to the new `LangChainInstrumentor` call |
| RAGAS (`ragas==0.4.3`) | RAG eval metrics (Section 5) | Opt-in only (`backend/requirements-eval.txt`, explicitly "DO NOT install into runtime") | pinned | Existing `eval_questionnaire_auto_answer.py` already has graceful-degrade `try/except ImportError` around RAGAS/OTel imports — new `eval_langchain/` tests should follow the identical pattern |

**Missing dependencies with no fallback:** the 9 LangChain packages themselves — must be installed for this phase to exist at all.
**Missing dependencies with fallback:** 9router/Ollama live-reachability (graceful `with_fallbacks` + circuit breaker already designed for this); Phoenix (graceful degrade already coded).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (no version pin found in `requirements.txt` grep this session — installed in `backend/venv`; run via `backend/venv/bin/python -m pytest` per CLAUDE.md/STATE.md convention, never bare `pytest`) |
| Config file | none — no `pytest.ini`/`[tool:pytest]` found; markers must be registered fresh (Pitfall E) |
| Quick run command | `backend/venv/bin/python -m pytest backend/tests/eval_langchain/ -m "eval and not llm" -q` (per AI-SPEC; requires Wave 0 marker registration) |
| Full suite command | `backend/venv/bin/python -m pytest backend/tests/ -q` (existing project convention; confirm 0 regressions against the last known-green baseline — 946 passed/22 skipped per STATE.md 2026-07-16) |

### Phase Requirement Support Map

> No standalone REQUIREMENTS.md IDs are registered for Phase 39 (per phase description — AI-SPEC.md is the requirements source). The table below maps AI-SPEC's 5 critical failure modes + Section 5 eval dimensions to concrete existing-vs-new test targets, standing in for a Req ID → Test map.

| AI-SPEC Anchor | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| Failure Mode 1 (cross-tenant leak) | Adversarial canary probes return zero cross-tenant hits | eval/code | `pytest backend/tests/eval_langchain/test_tenant_isolation.py -m eval -q` | ❌ Wave 0 — but the underlying `rag_service.query` tenant filter is already unit-tested in `test_rag_service_tenant_isolation.py` (Phase 30) |
| Failure Mode 2 (fabricated findings) | Citation validator rejects unresolvable chunk IDs | code | `pytest backend/tests/eval_langchain/test_citation_validator.py -m "eval and not llm" -q` | ❌ Wave 0 |
| Failure Mode 3 (optimistic status inflation) | False-pass rate = 0 on Critical/High gold controls | code | `pytest backend/tests/eval_langchain/test_conservative_status.py -m "eval and not llm" -q` | ❌ Wave 0 |
| Failure Mode 4 (unreviewed outbound claims) | RAG-02 state machine still blocks `submitted` without approver | code | existing `test_questionnaire_answer_review.py`-equivalent (Phase 30) — re-run unchanged against the new generation path | ✅ (Phase 30 test exists; confirm it still passes against the migrated generator, don't rewrite it) |
| Failure Mode 5 (silent fallback degradation) | Every fallback-provenance output carries `model_provenance` marker | code | `pytest backend/tests/eval_langchain/test_fallback_provenance.py -m "eval and not llm" -q` | ❌ Wave 0 |
| Regression guard | Full backend suite stays green | integration | `backend/venv/bin/python -m pytest backend/tests/ -q` | ✅ (existing suite; baseline 946 passed/22 skipped, 2026-07-16) |

### Sampling Rate
- **Per task commit:** targeted `pytest backend/tests/eval_langchain/ -m "eval and not llm" -q` (code-based, no token spend) plus the specific surface's existing test file (e.g. `test_questionnaire_answer_draft.py` if it exists — confirm name during planning) re-run to catch regressions from the auditor/questionnaire service becoming a thin shim.
- **Per wave merge:** full backend suite (`pytest backend/tests/ -q`).
- **Phase gate:** full suite green + the eval-marked suite green before `/gsd-verify-work`; RAGAS/LLM-judge dimensions are nightly per AI-SPEC, not a phase-gate blocker.

### Wave 0 Gaps
- [ ] `pytest.ini` or `pyproject.toml` `[tool.pytest.ini_options]` — register `eval` and `llm` markers (Pitfall E)
- [ ] `backend/tests/eval_langchain/` directory + `data/` fixtures subfolder (does not exist yet)
- [ ] `backend/tests/eval_langchain/conftest.py` — shared fixtures (two seeded eval tenants A/B per AI-SPEC Section 5 Reference Dataset spec)
- [ ] Framework install: `pip install "langchain==1.3.14" "langchain-openai==1.3.5" "langchain-ollama==1.1.0" "langchain-anthropic==1.4.8" "langgraph==1.2.9" "langgraph-checkpoint-sqlite==3.1.0" "openinference-instrumentation-langchain==0.1.67"` — gate each behind `checkpoint:human-verify` per Package Legitimacy Audit above (rubber-stamp, all pre-verified this session)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No (unchanged) | Existing `get_current_user`/`verify_agent_key` — this phase adds no new auth surface |
| V3 Session Management | Yes | LangGraph checkpointer `thread_id` = `f"{tenant_id}:{conversation_id}"` is a session-scoping control, not classic web session mgmt — treat tenant-prefix omission as the equivalent of session-fixation |
| V4 Access Control | Yes | Existing RBAC (`rbac_service.has_permission`, `require_permission`) gates every endpoint that will call the new agents; the agents themselves add no new access-control layer — tool-level tenant closure (Pitfall B) is the relevant control here, not V4's usual authz-check pattern |
| V5 Input Validation | Yes | Pydantic schemas (`AuditFinding`, `AnswerDraft`, `NarrativeOutput`, new `Citation`) — never hand-parsed JSON (Don't Hand-Roll table) |
| V6 Cryptography | No new surface | Existing Fernet-encrypted SaaS tokens/API keys unaffected; 9router/Ollama API keys pass through env vars / `system_settings`, unchanged storage |
| V13 API and Web Service (custom addition relevant here) | Yes | Prompt-injection via retrieved evidence content is the dominant threat for this phase (AI-SPEC's own domain research, Known Failure Mode 3) — mitigated structurally by never interpolating retrieved chunks into the system prompt (AI-SPEC Section 4b already specifies this correctly) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Prompt-injected evidence file instructing tenant-filter bypass | Elevation of Privilege / Tampering | Tenant ID closed over in `@tool` factory args, never a model-fillable parameter (Pattern in AI-SPEC entry point, Pitfall B reinforces why) |
| Citation ID fabrication (hallucinated `chunk_id`) | Repudiation / Tampering | Post-generation code validator resolving every citation against Chroma/`asset_compliance`/`control_evidence` before persisting (new — Pattern 3) |
| Silent event-loop blocking from sync `agent.invoke()` in an async endpoint | Denial of Service | Code-review grep rule `\.invoke\(|asyncio\.run\(` in `ai_orchestration/` (AI-SPEC Section 4b; this codebase has direct precedent — the rate-limiter shared-IP-bucket incident referenced in project memory was exactly this class of event-loop-blocking bug) |
| Two independent chat backends drifting in guardrail coverage (Pitfall A) | Information Disclosure | Explicit Wave-1 scope decision on which chat backend(s) actually route through the new guardrail-wrapped agent; do not assume both are covered by migrating one |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `langchain-chroma`'s embedding-function requirement is incompatible with `rag_service.py`'s implicit-default-embedding collection without an explicit `embedding_function=` argument matching Chroma's ONNX MiniLM default (this session read `rag_service.py` directly and confirmed no `embedding_function=` is passed to `get_or_create_collection`, consistent with AI-SPEC's own Pitfall 2 claim — not independently verified against `langchain-chroma`'s actual source this session, only cross-referenced against AI-SPEC's citation) | Don't Hand-Roll / Pattern 2 | If wrong in the safe direction (langchain-chroma actually handles the default case transparently), the cost is only over-caution — Pitfall 2's guidance to keep `rag_service.py` wrapped-not-rewrapped remains the correct choice regardless because it avoids a needless dependency and re-embed cost either way |
| A2 | No frontend component other than `ChatAssistant.tsx` currently calls `/api/assistant/chat` (Phase 38's grounded chat endpoint) — based on a single grep of `ChatAssistant.tsx`'s imports/fetches this session, not an exhaustive search of every `.tsx` file for `assistant/chat` | Pitfall A | If a different frontend surface already calls `/api/assistant/chat`, Pitfall A's "which chat backend to migrate" framing changes — the planner should grep `grep -rn "assistant/chat\|streamChatAssistant\|/api/assistant" components/ services/` before finalizing Wave 1 scope, this was not exhaustively done here |
| A3 | `agent_ai_decisions`'s existing document shape (`task_id`, `selected_tool`, agentic capability context) has no `surface` discriminator field today — based on a grep of write sites in `agentic_service.py`/`agentic_tasks_endpoints.py`, not a full schema dump of the collection's actual stored documents | Pitfall D | If some documents already carry a `surface` or similar field from other work, the "genuine architectural decision" framing in Pitfall D may already be partially resolved — worth a quick `db.agent_ai_decisions.find_one()` during planning |
| A4 | The 9router gateway and local Ollama are not confirmed live/reachable in the current dev environment this session (no network probe run against `AI_ROUTER_URL`/`OLLAMA_URL`) | Environment Availability | If 9router is actually down, eval/integration tests that assume the primary route works will need the fallback path exercised explicitly from the start, not discovered as a surprise mid-implementation |

## Open Questions

1. **Which chat surface does "migrate the chat assistant" actually mean?**
   - What we know: `agent_chat_endpoints.py` has no LLM call at all. `ai_service.chat()` (`/api/ai/chat`, used by `ChatAssistant.tsx`) is a hand-rolled demo/skill dispatcher with no RAG grounding. `ai_assistant_service.chat()` (`/api/assistant/chat`, Phase 38) is RAG-grounded with citations already, structurally closest to AI-SPEC's target shape.
   - What's unclear: whether the user/planner wants (a) `ChatAssistant.tsx` re-pointed at a migrated version of the Phase 38 assistant (a real, visible UX change), (b) the legacy `/api/ai/chat` demo-tour behavior preserved and separately migrated, or (c) only the Phase 38 assistant touched this phase with the legacy chat explicitly left alone.
   - Recommendation: surface this as an explicit AskUserQuestion-style decision in discuss-phase or Wave 1 planning before any chat-surface task is written — do not let the planner guess.

2. **Should `ai_auditor_service.py`/`compliance_narrative_service.py`/`questionnaire_answer_draft_service.py` be fully retired (deleted) once their LangChain replacements ship, or kept as thin compatibility shims?**
   - What we know: `ai_auditor_endpoints.py` imports `ai_auditor_service.get_auditor()` directly; `compliance_reports`/scheduled-report code paths call `compliance_narrative_service.enrich_report_data` directly; `questionnaire_answer_draft_service.draft_answer_for_question` is called from questionnaire endpoints not read this session.
   - What's unclear: the exact call sites and whether any test file imports these modules directly by name (a rename/retirement would break those imports even if behavior is identical).
   - Recommendation: `grep -rn "from ai_auditor_service\|from compliance_narrative_service\|from questionnaire_answer_draft_service"` across `backend/` (endpoints + tests) during planning to enumerate every caller before deciding shim-vs-delete.

3. **Does the 9router gateway's OpenAI-compatible wire format support the specific tool-calling / structured-output request shapes `create_agent`/`response_format` will send?**
   - What we know: `OpenAICompatProvider` today sends a bare `/v1/chat/completions` request with `messages`/`max_tokens`/optional `temperature` — no `tools`/`tool_choice`/`response_format` fields are ever sent by the existing code, so this is untested territory for the gateway itself (not just for this codebase).
   - What's unclear: whether the 9router gateway (a project-local proxy, not documented in the packages read this session) forwards `tools`/`response_format` fields transparently to Anthropic, or strips/rejects them.
   - Recommendation: Wave 0 should include a smoke-test task — a minimal `init_chat_model(...).invoke(...)` call with a trivial tool bound, run against the live 9router gateway — before committing to `create_agent` across all surfaces. This is the single highest-uncertainty integration point in the whole phase and is not resolvable by reading code; it requires hitting the actual gateway.

## Sources

### Primary (HIGH confidence — direct codebase reads, this session)
- `backend/ai_service.py`, `backend/ai_providers.py`, `backend/ai_auditor_service.py`, `backend/ai_auditor_endpoints.py`, `backend/ai_endpoints.py`, `backend/ai_assistant_service.py`, `backend/ai_assistant_endpoints.py`, `backend/agent_chat_endpoints.py`, `backend/rag_service.py`, `backend/compliance_narrative_service.py`, `backend/questionnaire_answer_draft_service.py`, `backend/questionnaire_answer_review_endpoints.py`, `backend/circuit_breaker.py`, `backend/tenant_context.py`, `backend/app_startup.py` (lines 440-500), `backend/router_registry.py`, `backend/tests/eval_questionnaire_auto_answer.py`, `backend/requirements.txt`, `backend/requirements-eval.txt`
- `pip index versions` direct PyPI query for all 9 LangChain-ecosystem packages (this session, `backend/venv/bin/pip`)
- `gsd-tools query package-legitimacy check --ecosystem pypi` (this session)
- `components/ChatAssistant.tsx`, `services/apiService.ts` (grep for API call targets)

### Secondary (MEDIUM confidence)
- `.planning/phases/39-langchain-ai-integration/39-AI-SPEC.md` — framework selection, LangChain quick-reference code patterns, evaluation strategy (already fetched from `docs.langchain.com` by `gsd-ai-researcher` per its own Sources section; not re-fetched independently this session, treated as authoritative per the phase's own upstream contract)

### Tertiary (LOW confidence)
- None — no unverified WebSearch-only claims introduced in this document beyond what AI-SPEC already carries with its own citations.

## Metadata

**Confidence breakdown:**
- Standard stack / versions: HIGH — every package version cross-checked directly against PyPI this session, matches AI-SPEC's pins exactly
- Codebase architecture map: HIGH — every file read directly this session, not inferred from the phase brief's description (which contained a factual error re: `agent_chat_endpoints.py`)
- LangChain-specific patterns (create_agent, ToolStrategy, etc.): MEDIUM — relies on AI-SPEC's own Context7/docs citations, not independently re-verified against `docs.langchain.com` this session
- 9router tool-calling compatibility (Open Question 3): LOW — genuinely unknown, needs a live smoke test, not resolvable by more reading

**Research date:** 2026-07-17
**Valid until:** ~14 days for the codebase-architecture claims (stable unless another phase touches these files first); ~30 days for the LangChain version pins (fast-moving ecosystem, AI-SPEC's own pins were fetched same-day as this research)
