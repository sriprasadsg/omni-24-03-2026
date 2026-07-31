# Phase 39: LangChain AI Integration - Pattern Map

**Mapped:** 2026-07-17
**Files analyzed:** 13 (new modules) + 3 (shim rewrites)
**Analogs found:** 12 / 13 (one net-new module — `tracing.py` — has a partial analog in `app_startup.py`)

## Scope Note

This is a new-code-alongside-old phase (per CONTEXT.md/RESEARCH.md), not a rename/migration. There is **no existing `backend/ai_orchestration/` directory** — every file below is net-new. The "analogs" here are the existing hand-rolled implementations that the new LangChain modules replace or wrap; the planner should treat them as "read this to know the exact behavior/contract to preserve," not "copy this LangChain-specific code," since none of the analogs use LangChain.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `backend/ai_orchestration/models.py` | service (model factory) | request-response | `backend/ai_service.py` (`get_provider_for_tenant`, `initialize`) | role-match (provider selection logic to replicate against `system_settings`) |
| `backend/ai_orchestration/agents/auditor.py` | service (agent) | request-response (batch-invoked) | `backend/ai_auditor_service.py` (`LocalAIAuditor.evaluate_evidence`) | exact (same responsibility, different implementation mechanism) |
| `backend/ai_orchestration/agents/chat.py` | service (agent) | request-response / streaming | `backend/ai_assistant_service.py` (`chat()`) | exact |
| `backend/ai_orchestration/agents/questionnaire.py` | service (agent) | CRUD (retrieve+generate+persist) | `backend/questionnaire_answer_draft_service.py` (`draft_answer_for_question`) | exact |
| `backend/ai_orchestration/agents/narrative.py` | service (agent) | request-response (embedded in batch PDF gen) | `backend/compliance_narrative_service.py` (`generate_executive_summary`) | exact |
| `backend/ai_orchestration/tools/retrieval.py` | utility (`@tool` wrapper) | request-response | `backend/rag_service.py` (`RagService.query`) | exact — wrap, do not reimplement |
| `backend/ai_orchestration/tools/evidence.py` | utility (`@tool` wrapper) | CRUD (read) | `backend/ai_auditor_endpoints.py` (evidence fetch: `db.asset_compliance.find(...)`, `controls_map` build) | role-match |
| `backend/ai_orchestration/schemas.py` | model (Pydantic) | transform | `backend/questionnaire_answer_draft_service.py` (`AnswerDraft`) + `backend/compliance_narrative_service.py` (`NarrativeOutput`) | exact — both are the existing "validated LLM output" pattern to generalize |
| `backend/ai_orchestration/prompts.py` | config/utility | transform | `backend/questionnaire_answer_draft_service.py` (`_build_prompt`) + `backend/compliance_narrative_service.py` system/user prompt blocks | role-match |
| `backend/ai_orchestration/memory.py` | service (checkpointer) | event-driven / stateful | none (net-new capability; nearest anti-pattern is `ai_service.py`'s `demo_sessions` in-process dict — explicitly NOT to be copied) | no analog (see below) |
| `backend/ai_orchestration/tracing.py` | config/utility | event-driven (span emission) | `backend/app_startup.py` (`init_agentic_tracing`, lines 468-496) | exact (structural twin — same try/except-degrade shape, new instrumentor) |
| `backend/ai_auditor_service.py` (shim rewrite) | service (shim) | request-response | itself (current file, full — 160 lines) | exact (must preserve `get_auditor()`/`evaluate_evidence()` public contract) |
| `backend/compliance_narrative_service.py` (shim rewrite) | service (shim) | request-response | itself (current file, full — 272 lines) | exact (preserve `generate_executive_summary`/`generate_framework_narrative`) |
| `backend/questionnaire_answer_draft_service.py` (shim rewrite) | service (shim) | CRUD | itself (current file, full — 216 lines) | exact (preserve `draft_answer_for_question` contract + Mongo doc shape) |
| `backend/tests/eval_langchain/*` | test | batch (eval) | `backend/tests/eval_questionnaire_auto_answer.py` (graceful `try/except ImportError` around RAGAS/OTel) | role-match |
| `backend/ai_assistant_endpoints.py` (if Wave-1 re-points chat) | route | streaming (SSE) | itself (current file, full — 116 lines) | exact — SSE framing (`_stream_answer`) must be preserved regardless of backend swap |

## Pattern Assignments

### `backend/ai_orchestration/models.py` (service, request-response)

**Analog:** `backend/ai_service.py`

**Provider-settings lookup pattern** (lines 74-94):
```python
db = get_database()
raw = db._db if hasattr(db, "_db") else db
settings = await raw.system_settings.find_one({"type": "llm", "tenantId": tenant_id})
if not settings:
    # No tenant-specific config → fall back to global provider
    if not self.is_configured:
        await self.initialize()
    return self.provider
provider = await _create_provider_from_settings(settings)
```

**Cache-invalidation pattern to reuse, not duplicate** (lines 57-62):
```python
self._tenant_providers: dict = {}  # cache: tenant_id → AIProvider

def invalidate_tenant_provider(self, tenant_id: Optional[str]) -> None:
    """Evict cached provider so next request re-reads from DB."""
    if tenant_id:
        self._tenant_providers.pop(tenant_id, None)
```
`models.py`'s `init_chat_model` factory MUST call this exact eviction method on settings change — do NOT add a second cache (RESEARCH.md Anti-Pattern: "Duplicating the provider-settings cache").

**Provider string values to map onto `init_chat_model(model_provider=...)`** (lines 106-154): env/settings values are `"router"/"9router"/"openai_compat"/"openai-compatible"` → OpenAI-compatible base_url; `"ollama"`; `"gemini"`; `"anthropic"/"claude"`. Env vars read unchanged: `AI_ROUTER_URL`, `AI_ROUTER_KEY`, `AI_ROUTER_MODEL`, `OLLAMA_URL`, `OLLAMA_MODEL`.

---

### `backend/ai_orchestration/agents/auditor.py` (service/agent, request-response)

**Analog:** `backend/ai_auditor_service.py` (full file, 160 lines) + `backend/ai_auditor_endpoints.py` (full file, 163 lines)

**Contract to preserve** — `get_auditor()` singleton + `evaluate_evidence(framework_name, control_desc, evidence_text) -> dict` return shape (lines 86-149):
```python
return {
    "verified": "PASS" in verdict,
    "reasoning": reasoning,
    "raw_response": raw,
    "evaluatedAt": now,
}
```
This shape is written directly into `db.asset_compliance` by the endpoint (`ai_auditor_endpoints.py` lines 117-122) — the new `AuditFinding` Pydantic schema's fields must still populate `verified`/`reasoning`/`evaluatedAt`/`model_used` or the endpoint's `set_fields` block needs a matching edit.

**Citation-source pattern (Pattern 3 from RESEARCH.md)** — control map + evidence fetch to reuse for the citation validator (`ai_auditor_endpoints.py` lines 63-100):
```python
controls_map = {c["id"]: c for c in framework.get("controls", [])}
asset_compliance = await db.asset_compliance.find(
    {"controlId": {"$in": list(controls_map.keys())}}
).to_list(length=500)
```
Citations must resolve against this same `asset_compliance`/`control_evidence` collection — no separate hardcoded map.

**Background-task invocation pattern to preserve** (endpoint lines 72-158): `background_tasks.add_task(run_ai_audit_task)` — the auditor agent's `ainvoke` calls must stay inside this existing background-task wrapper, not become a new sync blocking call in the request path.

**Fail-closed error handling** (lines 116-132):
```python
except Exception as e:
    logger.error("AI auditor inference failed: %s", e)
    return {"verified": False, "reasoning": f"Local AI inference error: {e}", "evaluatedAt": now}
...
if not raw or raw.startswith("BLOCKED:"):
    return {"verified": False, "reasoning": raw or "Local AI returned no response.", ...}
```

---

### `backend/ai_orchestration/agents/chat.py` (service/agent, request-response/streaming)

**Analog:** `backend/ai_assistant_service.py` (full file, 151 lines) + `backend/ai_assistant_endpoints.py` (full file, 116 lines)

**Imports pattern** (lines 1-16 of `ai_assistant_service.py`):
```python
import logging
import json
from typing import Any, Optional

from database import get_database
from rag_service import rag_service
from ai_service import ai_service
```

**Return-contract to preserve** — `chat(query, tenant_id, history) -> {"answer": str, "sources": [...]}` (lines 19-36, 152). Frontend/endpoint depends on this exact shape.

**Tenant-scoped RAG retrieval + defense-in-depth filter (Pattern 4 from RESEARCH.md)** (lines 40-58):
```python
raw_context = rag_service.query(query, n_results=5, tenant_id=tenant_id)
if raw_context:
    for item in raw_context:
        src_tenant = item.get("tenantId") or item.get("metadata", {}).get("tenantId", "")
        if src_tenant and src_tenant not in (tenant_id, "global"):
            continue
```
The new `@tool` wrapper in `tools/retrieval.py` must close over `tenant_id` as a factory argument here exactly as this call site already does — never read from a model-supplied argument (RESEARCH.md Pitfall B).

**SSE streaming pattern to preserve if Wave-1 rewires the endpoint** (`ai_assistant_endpoints.py` lines 55-83):
```python
async def _stream_answer(query, tenant_id, history) -> AsyncIterator[str]:
    result = await assistant_chat(query, tenant_id, history)
    answer = result.get("answer", ""); sources = result.get("sources", [])
    words = answer.split()
    for i, word in enumerate(words):
        yield f"data: {_json.dumps({'chunk': word + (' ' if i < len(words) - 1 else '')})}\n\n"
        await _asyncio.sleep(0.02)
    yield f"data: {_json.dumps({'sources': sources})}\n\n"
    yield "data: [DONE]\n\n"
```
If `create_agent` supports `.astream()`, this hand-rolled word-splitting loop is the thing LangChain streaming replaces — but the SSE frame format (`{"chunk":...}`, `{"sources":...}`, `[DONE]`) is a frontend contract and must be preserved regardless.

**RBAC/auth pattern** (`ai_assistant_endpoints.py` lines 26-30):
```python
current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
```

---

### `backend/ai_orchestration/agents/questionnaire.py` (service/agent, CRUD)

**Analog:** `backend/questionnaire_answer_draft_service.py` (full file, 216 lines)

**Contract to preserve** — Mongo document shape written to `questionnaire_answer_drafts` (lines 148-166), status machine `pending_review` never auto-advances (RAG-02 gate, Failure Mode 4):
```python
draft_doc = {
    "id": f"qad-{uuid.uuid4().hex}", "tenantId": tenant_id, "questionSetId": question_set_id,
    "questionId": question_id, "questionText": question_text,
    "answerText": draft.answer_text, "original_answer_text": draft.answer_text,
    "confidence": draft.confidence, "sourceEvidenceIds": draft.source_evidence_ids,
    "sourceEvidence": [...], "status": "pending_review",
    "created_at": ..., "updated_at": ...,
}
```

**Existing Pydantic validated-output pattern to generalize into `schemas.py`** (lines 64-91):
```python
class AnswerDraft(BaseModel):
    question_id: str
    answer_text: str
    confidence: str
    source_evidence_ids: List[str]
    word_count: int

    @field_validator("answer_text")
    @classmethod
    def not_empty_or_error_string(cls, v: str) -> str:
        ...
        if v.startswith(("BLOCKED:", "Error:")):
            raise ValueError(f"LLM returned error string: {v[:80]}")
        ...

    @model_validator(mode="after")
    def grounded_or_flagged(self) -> "AnswerDraft":
        if not self.source_evidence_ids and self.confidence != "insufficient_evidence":
            raise ValueError("answer has no source_evidence_ids but confidence != 'insufficient_evidence'")
        return self
```
This is the exact citation-required pattern AI-SPEC's `AuditFinding`/`citations: min_length=1` generalizes — reuse the validator shape, not the JSON-parsing mechanism around it (that's what `response_format=Schema` replaces).

**PII-scrub pre-prompt pattern to reuse in `prompts.py`** (lines 31-45):
```python
def _sanitise_chunk(chunk):
    content = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', "[REDACTED_EMAIL]", content)
    content = re.sub(r'\b(/workspace|/home/user)/[^\s]*\b', "", content)
    return {"source": chunk.get("source", ""), "content": content[:500]}
```

**tenant_context usage — DO NOT copy the `set_tenant_id`/`get_tenant_id()` call pattern into any `@tool` body** (line 107, `tenant_context.py` full file, 13 lines): this file's synchronous-linear-execution call to `set_tenant_id(tenant_id)` is safe here but is exactly the anti-pattern RESEARCH.md Pitfall B warns against inside LangGraph tool closures — new tools must take `tenant_id` as a captured factory argument instead.

---

### `backend/ai_orchestration/agents/narrative.py` (service/agent, request-response)

**Analog:** `backend/compliance_narrative_service.py` (lines 1-120 read; full file 272 lines)

**Imports pattern** (lines 1-13):
```python
import re
import html as _html
import logging
from pydantic import BaseModel, field_validator, model_validator, ValidationError

from ai_service import ai_service
from tenant_context import set_tenant_id
```

**Sanitization-before-prompt-interpolation pattern (prompt-injection guard)** (lines 26-30):
```python
def _sanitise(value: str, max_len: int = 200) -> str:
    value = _NEWLINES.sub(" ", str(value))
    return _UNSAFE.sub("", value).strip()[:max_len]
```

**Validated-output + graceful-fallback pattern** (lines 38-77, 89-117) — the exact pattern `schemas.py`'s shared validator should generalize:
```python
class NarrativeOutput(BaseModel):
    text: str
    word_count: int
    limit: int = 200

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("narrative text must not be empty")
        if v.startswith(("BLOCKED:", "Error:")):
            raise ValueError(f"LLM returned error string: {v[:80]}")
        return v

    @model_validator(mode="after")
    def within_budget(self) -> "NarrativeOutput":
        if self.word_count > self.limit:
            raise ValueError(f"narrative exceeds word budget: {self.word_count} words (limit {self.limit})")
        return self

def _validated_narrative(raw, fallback, limit=200):
    try:
        output = NarrativeOutput.from_raw(raw, limit=limit)
        return output.text
    except ValidationError as exc:
        logger.warning("[NarrativeService] Pydantic validation failed: %s", exc)
        return fallback
```
The fallback-on-validation-failure pattern (never letting a report generation hard-fail) should carry over into `agents/narrative.py`.

---

### `backend/ai_orchestration/tools/retrieval.py` (utility `@tool`, request-response)

**Analog:** `backend/rag_service.py` (full file, 104 lines) — **wrap, never rewrap** (RESEARCH.md Pattern 2 — no `langchain-chroma`).

**Exact function signature to wrap unchanged** (lines 58-78):
```python
def query(self, query_text: str, n_results: int = 3, tenant_id: str = None) -> list:
    query_kwargs = {"query_texts": [query_text], "n_results": n_results}
    if tenant_id:
        query_kwargs["where"] = {"$or": [{"tenantId": tenant_id}, {"tenantId": "global"}]}
    results = self.collection.query(**query_kwargs)
```
Confirmed: no `embedding_function=` passed to `get_or_create_collection` (line 23) — this is why `langchain-chroma` must NOT be installed/used this phase.

---

### `backend/ai_orchestration/tools/evidence.py` (utility `@tool`, CRUD)

**Analog:** `backend/ai_auditor_endpoints.py` (evidence-fetch block, lines 76-100)
```python
asset_compliance = await db.asset_compliance.find(
    {"controlId": {"$in": list(controls_map.keys())}}
).to_list(length=500)
```
Wrap this Mongo read as an `@tool get_control_evidence(control_id: str)` closed over `tenant_id`/`db`, per Pitfall B.

---

### `backend/ai_orchestration/tracing.py` (config, event-driven)

**Analog:** `backend/app_startup.py` (`init_agentic_tracing`, lines 468-496) — structural twin, swap instrumentor:
```python
def init_agentic_tracing() -> None:
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from openinference.instrumentation.anthropic import AnthropicInstrumentor

        endpoint = os.getenv("PHOENIX_OTLP_ENDPOINT", "http://localhost:4318/v1/traces")
        provider = TracerProvider()
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        trace.set_tracer_provider(provider)
        AnthropicInstrumentor().instrument()
        logger.info("[AgenticTracing] Phoenix tracing active at %s", endpoint)
    except ImportError:
        logger.warning("... not installed — agentic LLM calls will not be traced ...")
    except Exception as exc:
        logger.warning("[AgenticTracing] Failed to initialise tracing: %s", exc)
```
New code: add `LangChainInstrumentor().instrument(tracer_provider=provider)` inside this same function (or a sibling called from the same `run_startup_services()` call site, line 678) — reuse the identical try/except-degrade shape, do not add a second startup hook with different failure semantics.

---

## Shared Patterns

### Fail-open/fail-closed error strings (`"BLOCKED:"`/`"Error:"` sentinel convention)
**Source:** `backend/ai_service.py` (`generate_text` guardrail scan), consumed identically in `questionnaire_answer_draft_service.py` line 119, `compliance_narrative_service.py` line 113, `ai_auditor_service.py` line 126
**Apply to:** Every new agent module — `ai_service.generate_text()` remains the underlying guardrail/retry/circuit-breaker layer when `create_agent`'s model is NOT `init_chat_model` talking directly to 9router (RESEARCH.md Anti-Pattern: don't double-wrap). If `create_agent` bypasses `ai_service.generate_text` entirely (per AI-SPEC), these sentinel-string checks must be re-implemented as pre/post `ainvoke()` hooks instead of silently dropped.
```python
if raw.startswith(("BLOCKED:", "Error:")):
    # fail-closed / fallback path
```

### Tenant-scoped RAG isolation
**Source:** `backend/rag_service.py` lines 74-77 (server-side `$or` filter) + `backend/ai_assistant_service.py` lines 46-50 (client-side belt-and-braces filter)
**Apply to:** `tools/retrieval.py` — both layers must be preserved in the new `@tool` wrapper.

### tenant_id closed over, never model-supplied
**Source:** No existing LangChain analog (net-new pattern); anti-pattern to avoid is `tenant_context.get_tenant_id()` used synchronously in `questionnaire_answer_draft_service.py` line 107 and `compliance_narrative_service.py` line 11 import.
**Apply to:** Every `@tool`-decorated function in `ai_orchestration/tools/` — must take `tenant_id` as a factory-closure argument (per AI-SPEC's `build_audit_agent(tenant_id)` pattern), never call `get_tenant_id()` from inside a tool body (RESEARCH.md Pitfall B, code-review grep rule).

### Pydantic validated-LLM-output-with-fallback
**Source:** `AnswerDraft` (`questionnaire_answer_draft_service.py` lines 64-91) + `NarrativeOutput` (`compliance_narrative_service.py` lines 38-63)
**Apply to:** `schemas.py`'s new shared `Citation`/`AuditFinding` models — same `field_validator`/`model_validator(mode="after")` shape, same "reject empty/BLOCKED/Error string" guard, same "citations/evidence required unless explicitly flagged insufficient" invariant.

### Graceful-degrade startup wiring
**Source:** `backend/app_startup.py::init_agentic_tracing` (lines 468-496)
**Apply to:** `tracing.py`'s `LangChainInstrumentor` addition — try/except ImportError (log + continue) / except Exception (log + continue), never raise into `run_startup_services()`.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `backend/ai_orchestration/memory.py` (LangGraph checkpointer, `AsyncSqliteSaver`) | service | event-driven/stateful | No existing persistent conversation-memory pattern in the codebase. Existing `ai_service.py`'s `demo_sessions: dict` (line 56) is an in-process-only anti-pattern (RESEARCH.md: "already a real production bug today") — explicitly must NOT be used as a template. Planner should follow AI-SPEC Section 4's `AsyncSqliteSaver`/`thread_id = f"{tenant_id}:{conversation_id}"` prescription directly; no codebase precedent to reconcile against. |
| `backend/tests/eval_langchain/` (whole directory + `conftest.py`, `pytest.ini` marker registration) | test/config | batch (eval) | Directory does not exist; no `pytest.ini`/`pyproject.toml` marker registration exists anywhere in `backend/` (confirmed, RESEARCH.md Pitfall E). Nearest partial analog for the graceful-degrade-on-missing-optional-deps pattern is `backend/tests/eval_questionnaire_auto_answer.py`'s `try/except ImportError` around RAGAS/OTel — reuse that shape, but the marker registration itself and directory scaffolding are net-new. |

## Metadata

**Analog search scope:** `backend/ai_service.py`, `backend/ai_providers.py`, `backend/ai_auditor_service.py`, `backend/ai_auditor_endpoints.py`, `backend/ai_assistant_service.py`, `backend/ai_assistant_endpoints.py`, `backend/rag_service.py`, `backend/compliance_narrative_service.py`, `backend/questionnaire_answer_draft_service.py`, `backend/tenant_context.py`, `backend/app_startup.py`
**Files scanned:** 11 backend files read directly this session (full or targeted ranges); `backend/ai_orchestration/` and `backend/tests/eval_langchain/` confirmed non-existent via `ls`
**Pattern extraction date:** 2026-07-17
