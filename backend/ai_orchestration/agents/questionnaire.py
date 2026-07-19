"""Phase 39-08 — create_agent questionnaire draft generation (AISPEC-39-S4/S4b/S5/S6/S7).

Replaces `questionnaire_answer_draft_service.py`'s hand-rolled prompt +
`json.loads` extraction with a `create_agent` built on the shared model
factory (39-04) and the tenant-closed `search_evidence` tool (39-05),
producing a schema-validated `CitedAnswer` (39-03) that is always run
through the shared `validate_citations` (39-03) before it is returned. An
unresolvable citation, a guardrail block, or an agent/invocation failure all
resolve to a conservative `confidence="insufficient_evidence"` result —
this module never returns an unvalidated or fabricated-confident answer
(Critical Failure Mode #4: this surface produces contractual representations
to third parties).

`ROUTER_STRUCTURED_OUTPUT_PASSTHROUGH == "FAIL"` (39-02/39-04 decision) means
this module always requests structured output via `ToolStrategy`, never a
bare `response_format=CitedAnswer` — mirrors `agents/auditor.py`.

This module does NOT write to Mongo and does NOT know about
`questionnaire_answer_drafts` — persistence and the RAG-02
`status="pending_review"` human-approval gate live exclusively in
`questionnaire_answer_draft_service.py`'s shim, which maps the `DraftResult`
this module returns onto its own document shape. Every retrieved evidence
chunk is PII-scrubbed (`_sanitise_chunk`, copied in intent from the shim's
pre-existing sanitizer — kept local here rather than imported, since the
shim now imports FROM this module and a reverse import would be circular)
before it ever reaches the model as user-turn content; retrieved evidence is
never interpolated into the system prompt (AI-SPEC Section 4b).

Uses `ainvoke` only — no bare `invoke`, no `asyncio.run` (AI-SPEC Section 4b
"the auditor and questionnaire paths are await-only").
"""
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langgraph.checkpoint.memory import InMemorySaver
from opentelemetry import trace as _otel_trace

from ai_orchestration.decision_log import log_ai_decision
from ai_orchestration.guardrails import cross_tenant_output_scan, scan_input, scan_output
from ai_orchestration.memory import make_thread_id
from ai_orchestration.models import (
    ROUTER_STRUCTURED_OUTPUT_PASSTHROUGH,
    build_model_for_tenant,
    classify_chain_failure,
    fallback_ollama_url,
    model_provenance,
)
from ai_orchestration.prompts import PROMPT_VERSION, QUESTIONNAIRE_SYSTEM_PROMPT
from ai_orchestration.schemas import CitedAnswer
from ai_orchestration.tools.retrieval import make_search_evidence
from ai_orchestration.tracing import attach_span_attributes
from ai_orchestration.validators import validate_citations
from rag_service import rag_service

logger = logging.getLogger(__name__)

_SURFACE = "questionnaire"
_MAX_CHUNKS = 5
_HANDLE_ERRORS_MSG = (
    "Output did not match the CitedAnswer schema. Return every field; "
    "answer_text must not be empty. If evidence is insufficient, set "
    "confidence to 'insufficient_evidence' and explain why in answer_text."
)


@dataclass
class DraftResult:
    """Everything `questionnaire_answer_draft_service.py`'s shim needs to
    build/write its Mongo document — this module never writes to Mongo
    itself (persistence + the RAG-02 `pending_review` gate stay in the
    shim, the single place that owns them).

    `retrieved_evidence` carries the raw (unsanitized) chunks this module
    retrieved via `rag_service.query`, so the shim can populate its
    pre-existing `sourceEvidence` Mongo field without a second RAG query —
    an addition beyond the plan's literal field list, necessary to preserve
    the exact Mongo document shape (must_have) without double-retrieving.
    """

    answer_text: str
    confidence: str
    source_evidence_ids: List[str]
    model_provenance: str
    needs_review: bool
    retrieved_evidence: List[Dict[str, Any]] = field(default_factory=list)
    reason: Optional[str] = None


def _raw_db(db: Any) -> Any:
    """Unwrap `TenantIsolatedDatabase` to the raw Motor db when present —
    mirrors `agents/auditor.py`/`agents/chat.py`'s own unwrap for the same
    reason (non-exempt collections would otherwise get a second, conflicting
    `tenantId` filter injected on top of `validate_citations`'s explicit
    tenant+global `$or` scope)."""
    return getattr(db, "_db", db)


def _response_format():
    """Honor the 39-02/39-04 router structured-output passthrough decision:
    while `ROUTER_STRUCTURED_OUTPUT_PASSTHROUGH == "FAIL"`, always request
    structured output via `ToolStrategy` rather than a bare
    `response_format=CitedAnswer` (AI-SPEC Section 4b)."""
    if ROUTER_STRUCTURED_OUTPUT_PASSTHROUGH == "FAIL":
        return ToolStrategy(CitedAnswer, handle_errors=_HANDLE_ERRORS_MSG)
    return CitedAnswer


def _sanitise_chunk(chunk: Dict[str, Any]) -> Dict[str, Any]:
    """PII-scrub a single retrieved chunk before it reaches the model as
    user-turn content. Copied in intent from
    `questionnaire_answer_draft_service.py`'s pre-existing `_sanitise_chunk`
    (kept local rather than imported to avoid a circular import, since the
    shim now imports FROM this module)."""
    content = chunk.get("content", "")
    if not isinstance(content, str):
        content = str(content or "")
    content = content.replace("```json", "").replace("```", "").strip()
    content = re.sub(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[REDACTED_EMAIL]", content
    )
    content = re.sub(r"\b(/workspace|/home/user)/[^\s]*\b", "", content)
    content = " ".join(content.split())
    return {"source": chunk.get("source", ""), "id": chunk.get("id", ""), "content": content[:500]}


def _build_evidence_block(chunks: List[Dict[str, Any]]) -> str:
    """Sanitized, citation-ready evidence block — `[source: X | id: Y]` per
    chunk (mirrors `tools/retrieval.py::search_evidence`'s tag format) so the
    model can populate `CitedAnswer.citations[].chunk_id` from real ids."""
    cleaned = [_sanitise_chunk(c) for c in chunks]
    return "\n\n".join(f"[source: {c['source']} | id: {c['id']}]\n{c['content']}" for c in cleaned)


async def _tenant_model_names(tenant_id: Optional[str], raw_db: Any) -> tuple:
    """Best-effort primary/fallback model name lookup, solely to compare
    against `response_metadata` via `model_provenance()`. Mirrors
    `agents/auditor.py::_tenant_model_names`. Degrades to (None, None) on
    any failure; provenance stamping must never block a draft."""
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


def _attach_span(tenant_id: Optional[str], model_prov: str) -> None:
    try:
        span = _otel_trace.get_current_span()
        attach_span_attributes(
            span,
            tenant_id=tenant_id,
            surface=_SURFACE,
            prompt_version=PROMPT_VERSION,
            model_provenance=model_prov,
        )
    except Exception as exc:  # tracing must never block a draft
        logger.debug("[ai_orchestration.agents.questionnaire] span attribute attach failed: %s", exc)


async def _record_decision(
    db: Any,
    question_id: str,
    question_set_id: Optional[str],
    outcome: str,
    citation_validation: str,
    model_prov: str,
    started_at: datetime,
) -> None:
    # log_ai_decision never re-raises (39-05 contract) — a decision-log
    # failure must never block the draft.
    ref: Dict[str, str] = {"question_id": question_id}
    if question_set_id:
        ref["question_set_id"] = question_set_id
    await log_ai_decision(
        db,
        _SURFACE,
        outcome=outcome,
        prompt_version=PROMPT_VERSION,
        model_provenance=model_prov,
        citation_validation=citation_validation,
        ref=ref,
        started_at=started_at,
    )


def _insufficient_evidence_result(
    reason: str, retrieved: Optional[List[Dict[str, Any]]] = None
) -> DraftResult:
    """Fail-closed placeholder — never a fabricated confident answer. Used
    for every exit path that never reaches (or trusts) a model-produced
    structured response."""
    return DraftResult(
        answer_text="",
        confidence="insufficient_evidence",
        source_evidence_ids=[],
        model_provenance="primary",
        needs_review=False,
        retrieved_evidence=retrieved or [],
        reason=reason,
    )


async def generate_draft(
    question_id: str,
    question_text: str,
    tenant_id: Optional[str],
    db: Any,
    question_set_id: Optional[str] = None,
) -> DraftResult:
    """Draft a grounded answer for one questionnaire question via
    `create_agent`, citation-validated and guardrailed. Every exit path
    returns a `DraftResult` safe to persist — guardrail blocks, missing
    structured output, agent failures, and citation-validation failures are
    all resolved to a conservative `confidence="insufficient_evidence"`
    result before this function returns; the shim never sees a raw or
    unvalidated model response (AI-SPEC Section 6, Failure Mode 4).
    """
    started_at = datetime.now(timezone.utc)
    raw_db = _raw_db(db)

    # --- Retrieve tenant evidence up front: both the "no evidence"
    # short-circuit (mirrors the pre-existing shim behavior — never invoke
    # the model when there is nothing to ground an answer in) and the
    # sanitized evidence block handed to the model as user-turn content.
    retrieved = rag_service.query(question_text, _MAX_CHUNKS, tenant_id)
    if not retrieved:
        result = _insufficient_evidence_result("no_evidence_retrieved")
        _attach_span(tenant_id, "primary")
        await _record_decision(
            db, question_id, question_set_id, result.confidence, "n/a", "primary", started_at
        )
        return result

    # --- Pre-invoke guardrail: PII/injection scan on the question text ---
    input_scan = await scan_input(question_text, _SURFACE)
    if not input_scan.passed:
        result = _insufficient_evidence_result("input_guardrail_blocked", retrieved)
        _attach_span(tenant_id, "primary")
        await _record_decision(
            db, question_id, question_set_id, result.confidence, "n/a", "primary", started_at
        )
        return result

    # --- Build + run the agent ---
    try:
        model = await build_model_for_tenant(tenant_id, db, surface=_SURFACE)
        search_evidence = make_search_evidence(tenant_id or "")
        agent = create_agent(
            model=model,
            tools=[search_evidence],
            system_prompt=QUESTIONNAIRE_SYSTEM_PROMPT,
            response_format=_response_format(),
            checkpointer=InMemorySaver(),
        )
        evidence_block = _build_evidence_block(retrieved)
        user_content = (
            f"<evidence>\n{evidence_block}\n</evidence>\n\n"
            f"QUESTION (id={question_id}): {question_text}"
        )
        thread_id = make_thread_id(tenant_id or "unknown", f"questionnaire:{question_id}")
        raw_result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": user_content}]},
            config={"configurable": {"thread_id": thread_id}, "recursion_limit": 15},
        )
    except Exception as exc:
        # .with_fallbacks([local]) exhausted the WHOLE chain — router primary AND
        # local Ollama fallback both failed. Fail loud (see agents/auditor.py).
        reason, detail = classify_chain_failure(exc)
        primary_name, fallback_name = await _tenant_model_names(tenant_id, raw_db)
        logger.error(
            "[ai_orchestration.agents.questionnaire] MODEL CHAIN EXHAUSTED — primary "
            "AND local Ollama fallback both failed. question=%s tenant=%s reason=%s "
            "primary_model=%s fallback_model=%s@%s detail=%s",
            question_id, tenant_id, reason, primary_name, fallback_name,
            fallback_ollama_url(), detail,
        )
        result = _insufficient_evidence_result(reason, retrieved)
        _attach_span(tenant_id, "primary")
        await _record_decision(
            db, question_id, question_set_id, result.confidence, "n/a", "primary", started_at
        )
        return result

    answer = raw_result.get("structured_response") if isinstance(raw_result, dict) else None
    if answer is None:
        result = _insufficient_evidence_result("no_structured_response", retrieved)
        _attach_span(tenant_id, "primary")
        await _record_decision(
            db, question_id, question_set_id, result.confidence, "n/a", "primary", started_at
        )
        return result

    if answer.question_id != question_id:
        # Never trust a model-echoed question_id when the caller already
        # supplied the real one.
        answer = answer.model_copy(update={"question_id": question_id})

    # --- Provenance ---
    messages = raw_result.get("messages") if isinstance(raw_result, dict) else None
    last_message = _last_message_with_metadata(messages)
    primary_name, fallback_name = await _tenant_model_names(tenant_id, raw_db)
    model_prov = model_provenance(last_message, primary_name, fallback_name)
    _attach_span(tenant_id, model_prov)

    # --- Post-invoke guardrails (output PII/injection + cross-tenant scan) ---
    output_scan = await scan_output(answer.answer_text, _SURFACE)
    tenant_scan = await cross_tenant_output_scan(answer.answer_text, tenant_id or "", raw_db)
    if not output_scan.passed or not tenant_scan.passed:
        block_reason = output_scan.reason if not output_scan.passed else tenant_scan.reason
        result = _insufficient_evidence_result(block_reason, retrieved)
        await _record_decision(
            db, question_id, question_set_id, result.confidence, "n/a", model_prov, started_at
        )
        return result

    # --- Citation validation (shared 39-03 validator; AI-SPEC Section 6) ---
    citation_result, answer = await validate_citations(answer, tenant_id or "", raw_db)
    citation_validation = "pass" if citation_result.ok else "blocked"
    downgrade_reason = None if citation_result.ok else citation_result.detail

    # --- Fallback-provenance escalation (Failure Mode 5, generalized from
    # the auditor surface): a fallback-generated confident answer is flagged
    # for extra review attention. Every draft already always lands
    # `pending_review` (RAG-02) regardless of this flag.
    needs_review = model_prov.startswith("fallback") and answer.confidence != "insufficient_evidence"

    await _record_decision(
        db, question_id, question_set_id, answer.confidence, citation_validation, model_prov, started_at
    )
    return DraftResult(
        answer_text=answer.answer_text,
        confidence=answer.confidence,
        source_evidence_ids=list(answer.source_evidence_ids),
        model_provenance=model_prov,
        needs_review=needs_review,
        retrieved_evidence=retrieved,
        reason=downgrade_reason,
    )
