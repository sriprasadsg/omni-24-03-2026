"""Phase 39-07 — create_agent chat surface (AISPEC-39-S4/S4b/S6/S7).

Replaces `ai_assistant_service.py`'s inline RAG-context-building +
`ai_service.generate_text(prompt)` call with a `create_agent` built on the
shared model factory (39-04) and the tenant-closed `search_evidence` tool
(39-05), invoked with a persistent tenant-prefixed checkpointer
(`ai_orchestration.memory.checkpointer_lifespan` / `make_thread_id`) instead
of the old in-process `demo_sessions`-style dict this codebase has
elsewhere — that pattern is an explicitly-documented anti-pattern for real
conversation memory (39-AI-SPEC.md Pitfall 5) and is never used here.

Chat is the one Phase 39 surface AI-SPEC scopes as free-text output — no
`response_format=`/`ToolStrategy` structured output (Section 4b: "Await
whenever the output is structured ... The auditor and questionnaire paths
are await-only" implies chat is NOT one of those; streaming partial JSON to
a parser is a bug, chat streams free text instead). `chat()` (ainvoke, full
`{answer, sources}`) is the await path for the JSON endpoint; `astream_chat`
(async generator of `{"chunk": ...}` frames then a final `{"sources": ...}`
frame) is the stream path for the SSE endpoint — not yet wired into
`ai_assistant_endpoints.py::_stream_answer` (39-CONTEXT.md: re-pointing the
streaming endpoint at this path is a separate follow-up, not this plan).

The RAG-context-building and live-findings-fusion (failing controls +
open high/critical risks) logic below is preserved verbatim in intent from
`ai_assistant_service.chat()` — both the server-side `$or` tenant filter
inside `rag_service.query` and the client-side belt-and-braces skip of any
chunk tagged with another tenant's id (RESEARCH-Pat4) — so the returned
`sources` list keeps its exact `{type, id, title, snippet}` shape. The
`search_evidence` tool is *additionally* available to the agent (tenant_id
closed over in the tool factory, never model-supplied — RESEARCH.md
Pitfall B) so the model can issue further targeted lookups mid-turn; the
directly-fetched RAG/live-findings context guarantees deterministic,
citable sources even on a turn where the model never calls the tool.

Uses `ainvoke`/`astream` only — never a bare synchronous invoke call or a
fresh event loop spun up mid-request (39-AI-SPEC.md Section 4b code-review
rule).
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Optional

from langchain.agents import create_agent
from opentelemetry import trace as _otel_trace

from ai_orchestration.decision_log import log_ai_decision
from ai_orchestration.guardrails import cross_tenant_output_scan, scan_input, scan_output
from ai_orchestration.memory import checkpointer_lifespan, make_thread_id
from ai_orchestration.models import build_model_for_tenant, model_provenance
from ai_orchestration.prompts import CHAT_SYSTEM_PROMPT, PROMPT_VERSION
from ai_orchestration.tools.retrieval import make_search_evidence
from ai_orchestration.tracing import attach_span_attributes
from database import get_database
from rag_service import rag_service

logger = logging.getLogger(__name__)

_SURFACE = "chat"
# AI-SPEC Section 4b: "Chat: trim to the last ~20 messages before invoke."
_MAX_HISTORY_MESSAGES = 20
_DEFAULT_CONVERSATION_ID = "default"
_BLOCKED_ANSWER_PREFIX = "I can't answer that right now"


def _raw_db(db: Any) -> Any:
    """Unwrap `TenantIsolatedDatabase` to the raw Motor db when present —
    mirrors `ai_orchestration/models.py` / `agents/auditor.py`'s own unwrap
    for the same reason (non-exempt collections would otherwise get a
    second, conflicting `tenantId` filter injected on top of the explicit
    tenant scoping already applied by the queries below)."""
    return getattr(db, "_db", db)


async def _tenant_model_names(tenant_id: Optional[str], raw_db: Any) -> tuple:
    """Best-effort primary/fallback model name lookup, solely to compare
    against `response_metadata` via `model_provenance()`. Degrades to
    (None, None) on any failure — provenance stamping must never block an
    answer. Mirrors `agents/auditor.py::_tenant_model_names`."""
    try:
        settings = None
        if tenant_id:
            settings = await raw_db.system_settings.find_one({"type": "llm", "tenantId": tenant_id})
        settings = settings or {}
        primary_name = settings.get("model") or "claude-sonnet-4-6"
        fallback_name = settings.get("ollamaModel") or "llama3.2:3b"
        return primary_name, fallback_name
    except Exception:
        return None, None


def _last_message_with_metadata(messages):
    for msg in reversed(messages or []):
        if getattr(msg, "response_metadata", None):
            return msg
    return messages[-1] if messages else None


async def _live_findings(tenant_id: str, raw_db: Any) -> tuple[list[str], list[dict]]:
    """Unchanged in intent from `ai_assistant_service.chat()`: failing
    controls (last 30 days) + open high/critical risks, as both prompt
    context and `sources` entries. Degrades to an explicit
    "unavailable" context note on any query failure — never raises."""
    context_parts: list[str] = []
    sources: list[dict] = []
    try:
        tenant_filter = {"tenantId": tenant_id}
        thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

        failed_controls = await raw_db.compliance_evidence.find(
            {**tenant_filter, "status": {"$in": ["FAILED", "FAIL"]}, "updatedAt": {"$gte": thirty_days_ago}},
            {"controlId": 1, "title": 1, "framework": 1, "status": 1, "updatedAt": 1},
        ).to_list(length=20)

        controls_summary = [
            f"- Control {c.get('controlId')}: {c.get('title', 'N/A')} "
            f"({c.get('framework', 'N/A')}) — {c.get('status', 'FAIL')}"
            for c in failed_controls
        ]
        if controls_summary:
            context_parts.append(
                "[COMPLIANCE] Failing controls (last 30 days):\n" + "\n".join(controls_summary[:10])
            )
            for c in failed_controls[:5]:
                sources.append({
                    "type": "compliance_control",
                    "id": c.get("controlId", ""),
                    "title": c.get("title", "N/A"),
                    "snippet": f"{c.get('framework', '')} — {c.get('status', 'FAIL')}",
                })

        risks = await raw_db.risks.find(
            {**tenant_filter, "status": {"$ne": "Closed"}, "severity": {"$in": ["Critical", "High"]}},
            {"id": 1, "title": 1, "severity": 1, "status": 1},
        ).to_list(length=10)

        risk_summary = [
            f"- Risk {r.get('id', 'N/A')}: {r.get('title', 'N/A')} [{r.get('severity', 'N/A')}]"
            for r in risks
        ]
        if risk_summary:
            context_parts.append("[RISKS] Open high/critical risks:\n" + "\n".join(risk_summary))
            for r in risks[:3]:
                sources.append({
                    "type": "risk",
                    "id": r.get("id", ""),
                    "title": r.get("title", "N/A"),
                    "snippet": f"{r.get('severity', 'N/A')} — {r.get('status', 'Open')}",
                })
    except Exception as exc:
        logger.warning("[ai_orchestration.agents.chat] Live findings query failed: %s", exc)
        context_parts.append("[DATA] Live findings temporarily unavailable.")
    return context_parts, sources


def _rag_context(query: str, tenant_id: str) -> tuple[list[str], list[dict]]:
    """Unchanged in intent from `ai_assistant_service.chat()`: direct RAG
    query for both prompt context and the deterministic `sources` list,
    independent of whatever the agent's own `search_evidence` tool call
    additionally retrieves mid-turn. Both isolation layers preserved: the
    server-side `$or` filter inside `rag_service.query` itself, and this
    client-side belt-and-braces skip of any chunk tagged with a tenant id
    that is neither the acting tenant nor "global"."""
    context_parts: list[str] = []
    sources: list[dict] = []
    raw_context = rag_service.query(query, n_results=5, tenant_id=tenant_id)
    if raw_context:
        for item in raw_context:
            src_tenant = item.get("tenantId") or item.get("metadata", {}).get("tenantId", "")
            if src_tenant and src_tenant not in (tenant_id, "global"):
                continue
            snippet = (item.get("content") or "")[:300]
            context_parts.append(f"[RAG] {snippet}")
            sources.append({
                "type": "rag",
                "id": item.get("id", ""),
                "title": item.get("source") or item.get("metadata", {}).get("source", "knowledge base"),
                "snippet": snippet,
            })
    return context_parts, sources


def _trim_history(history: Optional[list[dict[str, str]]]) -> list[dict[str, str]]:
    if not history:
        return []
    return list(history[-_MAX_HISTORY_MESSAGES:])


def _history_block(history: Optional[list[dict[str, str]]]) -> str:
    block = ""
    for turn in _trim_history(history):
        role = turn.get("role", "user")
        block += f"\n{role.capitalize()}: {turn.get('content', '')}"
    return block


def _build_user_content(query: str, context_parts: list[str], history: Optional[list[dict[str, str]]]) -> str:
    context_block = "\n\n".join(context_parts) if context_parts else "(No relevant context found.)"
    return (
        f"## Context\n{context_block}\n\n"
        f"## Conversation history\n{_history_block(history)}\n\n"
        f"User: {query}"
    )


def _attach_span(tenant_id: Optional[str], model_prov: str) -> None:
    try:
        span = _otel_trace.get_current_span()
        attach_span_attributes(
            span, tenant_id=tenant_id, surface=_SURFACE,
            prompt_version=PROMPT_VERSION, model_provenance=model_prov,
        )
    except Exception as exc:  # tracing must never block an answer
        logger.debug("[ai_orchestration.agents.chat] span attribute attach failed: %s", exc)


async def _record_decision(db: Any, thread_id: str, outcome: str, model_prov: str, started_at: datetime) -> None:
    # log_ai_decision never re-raises (39-05 contract) — a decision-log
    # failure must never block the chat answer.
    await log_ai_decision(
        db, _SURFACE, outcome=outcome, prompt_version=PROMPT_VERSION,
        model_provenance=model_prov, ref={"thread_id": thread_id}, started_at=started_at,
    )


def _blocked_result(reason: str) -> dict[str, Any]:
    return {"answer": f"{_BLOCKED_ANSWER_PREFIX}: {reason}.", "sources": []}


async def chat(
    query: str,
    tenant_id: str,
    history: Optional[list[dict[str, str]]] = None,
    conversation_id: Optional[str] = None,
    db: Any = None,
) -> dict[str, Any]:
    """Answer a tenant-scoped security/compliance question via `create_agent`.

    Preserves `ai_assistant_service.chat()`'s exact `{answer, sources}`
    contract. `db` defaults to `database.get_database()` when not supplied —
    the shim in `ai_assistant_service.py` passes its own resolved handle.
    ainvoke-only (await path); see `astream_chat` for the SSE-streaming
    counterpart.
    """
    started_at = datetime.now(timezone.utc)
    db = db if db is not None else get_database()
    raw_db = _raw_db(db)
    thread_id = make_thread_id(tenant_id or "unknown", conversation_id or _DEFAULT_CONVERSATION_ID)

    # --- Pre-invoke guardrail: PII/injection scan on the user's query ---
    input_scan = await scan_input(query, _SURFACE)
    if not input_scan.passed:
        _attach_span(tenant_id, "primary")
        await _record_decision(db, thread_id, "input_guardrail_blocked", "primary", started_at)
        return _blocked_result("your message was flagged by an input safety check")

    findings_context, findings_sources = await _live_findings(tenant_id, raw_db)
    rag_context_parts, rag_sources = _rag_context(query, tenant_id)
    sources = rag_sources + findings_sources
    user_content = _build_user_content(query, rag_context_parts + findings_context, history)

    # --- Build + run the agent ---
    try:
        model = await build_model_for_tenant(tenant_id, db, surface=_SURFACE)
        search_evidence = make_search_evidence(tenant_id or "")
        async with checkpointer_lifespan() as checkpointer:
            agent = create_agent(
                model=model,
                tools=[search_evidence],
                system_prompt=CHAT_SYSTEM_PROMPT,
                checkpointer=checkpointer,
            )
            result = await agent.ainvoke(
                {"messages": [{"role": "user", "content": user_content}]},
                config={"configurable": {"thread_id": thread_id}, "recursion_limit": 15},
            )
    except Exception as exc:
        logger.error("[ai_orchestration.agents.chat] agent run failed tenant=%s: %s", tenant_id, exc)
        _attach_span(tenant_id, "primary")
        await _record_decision(db, thread_id, "agent_invocation_error", "primary", started_at)
        return {"answer": f"Error generating response: {exc}", "sources": []}

    messages = result.get("messages") if isinstance(result, dict) else None
    last_message = _last_message_with_metadata(messages)
    answer = getattr(last_message, "content", "") or ""

    primary_name, fallback_name = await _tenant_model_names(tenant_id, raw_db)
    model_prov = model_provenance(last_message, primary_name, fallback_name)
    _attach_span(tenant_id, model_prov)

    # --- Post-invoke guardrails (output PII/injection + cross-tenant scan) ---
    output_scan = await scan_output(answer, _SURFACE)
    tenant_scan = await cross_tenant_output_scan(answer, tenant_id or "", raw_db)
    if not output_scan.passed or not tenant_scan.passed:
        reason = output_scan.reason if not output_scan.passed else tenant_scan.reason
        await _record_decision(db, thread_id, reason, model_prov, started_at)
        return _blocked_result("the response was flagged by a safety check")

    await _record_decision(db, thread_id, "answered", model_prov, started_at)
    return {"answer": answer, "sources": sources}


async def astream_chat(
    query: str,
    tenant_id: str,
    history: Optional[list[dict[str, str]]] = None,
    conversation_id: Optional[str] = None,
    db: Any = None,
) -> AsyncIterator[dict[str, Any]]:
    """Async-generator counterpart to `chat()` for the SSE streaming
    endpoint (AI-SPEC Section 4b: stream via `astream` for the chat
    assistant — UX only, never partial structured output). Yields
    `{"chunk": token}` frames as they arrive, then a final `{"sources": [...]}`
    frame, or `{"error": ...}` on a guardrail block/agent failure — the
    caller maps these onto the existing SSE `data: ...` frame contract.
    Not yet called by `ai_assistant_endpoints.py` this plan (39-CONTEXT.md).
    """
    started_at = datetime.now(timezone.utc)
    db = db if db is not None else get_database()
    raw_db = _raw_db(db)
    thread_id = make_thread_id(tenant_id or "unknown", conversation_id or _DEFAULT_CONVERSATION_ID)

    input_scan = await scan_input(query, _SURFACE)
    if not input_scan.passed:
        await _record_decision(db, thread_id, "input_guardrail_blocked", "primary", started_at)
        yield {"error": "your message was flagged by an input safety check"}
        return

    findings_context, findings_sources = await _live_findings(tenant_id, raw_db)
    rag_context_parts, rag_sources = _rag_context(query, tenant_id)
    sources = rag_sources + findings_sources
    user_content = _build_user_content(query, rag_context_parts + findings_context, history)

    full_answer = ""
    try:
        model = await build_model_for_tenant(tenant_id, db, surface=_SURFACE)
        search_evidence = make_search_evidence(tenant_id or "")
        async with checkpointer_lifespan() as checkpointer:
            agent = create_agent(
                model=model,
                tools=[search_evidence],
                system_prompt=CHAT_SYSTEM_PROMPT,
                checkpointer=checkpointer,
            )
            async for chunk_msg, _meta in agent.astream(
                {"messages": [{"role": "user", "content": user_content}]},
                config={"configurable": {"thread_id": thread_id}, "recursion_limit": 15},
                stream_mode="messages",
            ):
                token = getattr(chunk_msg, "content", "")
                if token:
                    full_answer += token
                    yield {"chunk": token}
    except Exception as exc:
        logger.error("[ai_orchestration.agents.chat] astream failed tenant=%s: %s", tenant_id, exc)
        await _record_decision(db, thread_id, "agent_invocation_error", "primary", started_at)
        yield {"error": f"Error generating response: {exc}"}
        return

    # Per-token provenance metadata isn't reliably available across all
    # providers via stream_mode="messages"; the streaming path stamps
    # "primary" and relies on the await path (`chat()`) for authoritative
    # fallback-provenance stamping.
    model_prov = "primary"
    output_scan = await scan_output(full_answer, _SURFACE)
    tenant_scan = await cross_tenant_output_scan(full_answer, tenant_id or "", raw_db)
    if not output_scan.passed or not tenant_scan.passed:
        await _record_decision(db, thread_id, "output_guardrail_blocked", model_prov, started_at)
        yield {"error": "the response was flagged by a safety check"}
        return

    await _record_decision(db, thread_id, "answered", model_prov, started_at)
    yield {"sources": sources}
