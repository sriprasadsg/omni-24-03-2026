"""Phase 39-06 — create_agent-based compliance auditor (AISPEC-39-S4/S4b/S6/S7).

Replaces `ai_auditor_service.py`'s raw VERDICT/REASONING text parse with a
`create_agent` built on the shared model factory (39-04) and tenant-closed
tools (39-05), producing a schema-validated `AuditFinding`
(citations `min_length=1`) that is always run through the shared
`validate_citations` (39-03) before it is returned. An unresolvable citation
or unknown `control_id` downgrades the finding to `insufficient_evidence`
with reason `citation_validation_failed` — this module never returns an
unvalidated finding.

`ROUTER_STRUCTURED_OUTPUT_PASSTHROUGH == "FAIL"` (39-02/39-04 decision) means
this module always requests structured output via `ToolStrategy`, never a
bare `response_format=AuditFinding` (AI-SPEC Section 4b: ToolStrategy on the
fallback/uncertain-passthrough route).

`db` handling note: `compliance_frameworks` is tenant-isolation-EXEMPT
(`database.py`) but `asset_compliance`/`control_evidence`/`system_settings`
are NOT — `TenantIsolatedCollection` auto-injects a top-level `tenantId`
equality filter that would silently exclude `tenantId: "global"` KB records
from `validate_citations`'s explicit `$or` scope query. This module
therefore unwraps to the raw db handle (`db._db` when present) before
passing it to `validate_citations`/`make_get_control_evidence`/tenant model
settings lookups — the same defensive unwrap `ai_orchestration/models.py`
already applies for the same reason. `log_ai_decision` gets the ORIGINAL
(possibly wrapped) `db`, since it relies on `TenantIsolatedCollection`'s
auto-injection for `insert_one` (its own docstring).
"""
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

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
    model_provenance,
)
from ai_orchestration.prompts import AUDITOR_SYSTEM_PROMPT, PROMPT_VERSION
from ai_orchestration.schemas import AuditFinding, Citation
from ai_orchestration.tools.evidence import make_get_control_evidence
from ai_orchestration.tools.retrieval import make_search_evidence
from ai_orchestration.tracing import attach_span_attributes
from ai_orchestration.validators import extract_control_id_tokens, validate_citations

logger = logging.getLogger(__name__)

_SURFACE = "auditor"
_UNKNOWN_CONTROL_ID = "UNSPECIFIED"
_HANDLE_ERRORS_MSG = (
    "Output did not match the AuditFinding schema. Return every field; "
    "citations must not be empty."
)


@dataclass
class AuditEvaluationResult:
    """Everything a caller (the `ai_auditor_service.py` shim, or a future
    direct caller) needs to act on one control assessment."""

    finding: AuditFinding
    model_provenance: str
    citation_validation: str
    needs_review: bool


def _raw_db(db: Any) -> Any:
    """Unwrap `TenantIsolatedDatabase` to the raw Motor db when present —
    mirrors `ai_orchestration/models.py`'s own unwrap for the same reason
    (non-exempt collections would otherwise get a second, conflicting
    tenantId filter injected on top of `validate_citations`'s explicit
    tenant+global `$or` scope)."""
    return getattr(db, "_db", db)


def _response_format():
    """Honor the 39-02/39-04 router structured-output passthrough decision:
    while `ROUTER_STRUCTURED_OUTPUT_PASSTHROUGH == "FAIL"`, always request
    structured output via `ToolStrategy` rather than a bare
    `response_format=AuditFinding` (AI-SPEC Section 4b)."""
    if ROUTER_STRUCTURED_OUTPUT_PASSTHROUGH == "FAIL":
        return ToolStrategy(AuditFinding, handle_errors=_HANDLE_ERRORS_MSG)
    return AuditFinding


def _insufficient_evidence_finding(control_id: str, reason: str, detail: str = "") -> AuditFinding:
    """Fail-closed placeholder — never a fabricated pass. Used for every exit
    path that never reaches (or trusts) a model-produced structured response."""
    rationale = f"insufficient_evidence: {reason}"
    if detail:
        rationale = f"{rationale} ({detail[:300]})"
    return AuditFinding(
        control_id=control_id or _UNKNOWN_CONTROL_ID,
        status="insufficient_evidence",
        rationale=rationale,
        citations=[Citation(source="ai_orchestration.agents.auditor", chunk_id="n/a")],
    )


async def _tenant_model_names(tenant_id: Optional[str], raw_db: Any) -> tuple:
    """Best-effort primary/fallback model name lookup, solely to compare
    against `response_metadata` via `model_provenance()`. Mirrors the same
    `system_settings` read `models.py` performs — never a second cache, just
    a read for provenance stamping. Degrades to (None, None) on any failure;
    provenance stamping must never block a finding."""
    try:
        settings = None
        if tenant_id:
            settings = await raw_db.system_settings.find_one({"type": "llm", "tenantId": tenant_id})
        settings = settings or {}
        primary_name = settings.get("model") or os.getenv("AI_ROUTER_MODEL") or "claude-sonnet-4-6"
        fallback_name = settings.get("ollamaModel") or os.getenv(
            "OLLAMA_MODEL", os.getenv("LLM_MODEL", "llama3.2:3b")
        )
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
    except Exception as exc:  # tracing must never block an evaluation
        logger.debug("[ai_orchestration.agents.auditor] span attribute attach failed: %s", exc)


async def _record_decision(
    db: Any,
    control_id: str,
    outcome: str,
    citation_validation: str,
    model_prov: str,
    started_at: datetime,
) -> None:
    # log_ai_decision already never re-raises (39-05 contract); the shared
    # (possibly tenant-isolated) db is used here so insert_one's own
    # tenantId auto-injection applies, per that module's docstring.
    await log_ai_decision(
        db,
        _SURFACE,
        outcome=outcome,
        prompt_version=PROMPT_VERSION,
        model_provenance=model_prov,
        citation_validation=citation_validation,
        ref={"control_id": control_id},
        started_at=started_at,
    )


async def evaluate_control(
    framework_name: str,
    control_desc: str,
    evidence_text: str,
    tenant_id: Optional[str],
    db: Any,
    control_id: Optional[str] = None,
) -> AuditEvaluationResult:
    """Assess a single control via `create_agent`, citation-validated and
    guardrailed. Every exit path returns an `AuditEvaluationResult` whose
    `.finding` is safe to persist/display — guardrail blocks, missing
    structured output, citation-validation failures, and fallback-provenance
    passes are all resolved to a conservative, already-downgraded-where-
    necessary `AuditFinding` before this function returns; callers never see
    a raw/unvalidated model response (AI-SPEC Section 6, Failure Modes 2/3/5).

    `control_id` is pinned onto the returned finding when the caller supplies
    it (defense-in-depth against a model-fabricated control_id, on top of the
    structural `validate_citations` framework-fidelity check below). When the
    caller does not know it, this best-effort-extracts a control-ID-shaped
    token from `control_desc` via `extract_control_id_tokens`; when none is
    found the finding conservatively stays unidentified (`UNSPECIFIED`),
    which correctly fails framework-fidelity resolution and downgrades to
    `insufficient_evidence` — "we don't know which control this is" is
    itself a fail-closed outcome, never a guess.
    """
    started_at = datetime.now(timezone.utc)
    resolved_control_id = (control_id or "").strip()
    if not resolved_control_id:
        tokens = extract_control_id_tokens(control_desc)
        resolved_control_id = tokens[0] if tokens else _UNKNOWN_CONTROL_ID

    raw_db = _raw_db(db)

    # --- Pre-invoke guardrail: PII/injection scan on user-supplied input ---
    input_text = f"{framework_name}\n{control_desc}\n{evidence_text}"
    input_scan = await scan_input(input_text, _SURFACE)
    if not input_scan.passed:
        finding = _insufficient_evidence_finding(
            resolved_control_id, "input_guardrail_blocked", "; ".join(input_scan.findings)
        )
        _attach_span(tenant_id, "primary")
        await _record_decision(db, resolved_control_id, finding.status, "n/a", "primary", started_at)
        return AuditEvaluationResult(finding, "primary", "n/a", False)

    # --- Build + run the agent ---
    try:
        model = await build_model_for_tenant(tenant_id, db, surface=_SURFACE)
        search_evidence = make_search_evidence(tenant_id or "")
        get_control_evidence = make_get_control_evidence(tenant_id or "", raw_db)
        agent = create_agent(
            model=model,
            tools=[search_evidence, get_control_evidence],
            system_prompt=AUDITOR_SYSTEM_PROMPT,
            response_format=_response_format(),
            checkpointer=InMemorySaver(),
        )
        user_content = (
            f"Framework: {framework_name}\n"
            f"Control ID: {resolved_control_id}\n"
            f"Requirement: {control_desc}\n"
            f"Collected evidence:\n{evidence_text[:6000]}"
        )
        thread_id = make_thread_id(tenant_id or "unknown", f"audit:{resolved_control_id}")
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": user_content}]},
            config={"configurable": {"thread_id": thread_id}, "recursion_limit": 25},
        )
    except Exception as exc:
        logger.error(
            "[ai_orchestration.agents.auditor] agent run failed control=%s tenant=%s: %s",
            resolved_control_id, tenant_id, exc,
        )
        finding = _insufficient_evidence_finding(resolved_control_id, "agent_invocation_error", str(exc))
        _attach_span(tenant_id, "primary")
        await _record_decision(db, resolved_control_id, finding.status, "n/a", "primary", started_at)
        return AuditEvaluationResult(finding, "primary", "n/a", False)

    finding = result.get("structured_response") if isinstance(result, dict) else None
    if finding is None:
        finding = _insufficient_evidence_finding(resolved_control_id, "no_structured_response")
        _attach_span(tenant_id, "primary")
        await _record_decision(db, resolved_control_id, finding.status, "n/a", "primary", started_at)
        return AuditEvaluationResult(finding, "primary", "n/a", False)

    if control_id:
        # Never trust a model-fabricated control_id when the caller already
        # knows the real one — structural mitigation on top of the citation
        # validator's framework-fidelity check below.
        finding = finding.model_copy(update={"control_id": control_id})

    # --- Provenance ---
    messages = result.get("messages") if isinstance(result, dict) else None
    last_message = _last_message_with_metadata(messages)
    primary_name, fallback_name = await _tenant_model_names(tenant_id, raw_db)
    model_prov = model_provenance(last_message, primary_name, fallback_name)
    _attach_span(tenant_id, model_prov)

    # --- Post-invoke guardrails (output PII/injection + cross-tenant scan) ---
    output_scan = await scan_output(finding.rationale, _SURFACE)
    tenant_scan = await cross_tenant_output_scan(finding.rationale, tenant_id or "", raw_db)
    if not output_scan.passed or not tenant_scan.passed:
        reason = output_scan.reason if not output_scan.passed else tenant_scan.reason
        finding = _insufficient_evidence_finding(resolved_control_id, reason)
        await _record_decision(db, resolved_control_id, finding.status, "n/a", model_prov, started_at)
        return AuditEvaluationResult(finding, model_prov, "n/a", False)

    # --- Citation + control-ID (framework-fidelity) validation ---
    citation_result, finding = await validate_citations(finding, tenant_id or "", raw_db)
    citation_validation = "pass" if citation_result.ok else "blocked"

    # --- Fallback-provenance escalation (Failure Mode 5) ---
    needs_review = model_prov.startswith("fallback") and finding.status == "pass"

    await _record_decision(db, resolved_control_id, finding.status, citation_validation, model_prov, started_at)
    return AuditEvaluationResult(finding, model_prov, citation_validation, needs_review)
