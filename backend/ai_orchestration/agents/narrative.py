"""Phase 39-09 — create_agent narrative generation (AISPEC-39-S4/S4b/S6/S7).

Replaces `compliance_narrative_service.py`'s hand-rolled
`ai_service.generate_text` + regex/word-trim path with a `create_agent`
built on the shared model factory (39-04), producing a schema-validated
`NarrativeOutput` (39-03) for both the executive summary and per-framework
findings narratives embedded in scheduled PDF reports. This surface needs no
retrieval tool (it summarizes data already supplied by the caller), so no
`search_evidence`/`get_control_evidence` tool is wired in — unlike
`agents/auditor.py`/`agents/questionnaire.py`.

`ROUTER_STRUCTURED_OUTPUT_PASSTHROUGH == "FAIL"` (39-02/39-04 decision) means
this module always requests structured output via `ToolStrategy`, never a
bare `response_format=NarrativeOutput` — mirrors `agents/auditor.py`/
`agents/questionnaire.py`.

Word-budget enforcement never trusts the model's self-reported
`NarrativeOutput.word_count`/`.limit` fields: this module always recomputes
`NarrativeOutput.from_raw(structured.text, limit=<call-site budget>)` from
the actual returned text before treating anything as validated (the same
"recompute, never trust a self-report" posture `validators.py` applies to
citations/control-ids). A validation failure (empty text, a `BLOCKED:`/
`Error:` guardrail sentinel, or an over-budget narrative), a guardrail
block, an unresolved framework-fidelity token (T-39-09-B), or any agent
exception all resolve to the same deterministic fallback narrative string
the pre-39-09 service used — this module NEVER raises and NEVER returns an
unvalidated narrative; the scheduled-report PDF pipeline must not hard-fail
on a model/gateway failure (T-39-09-C, AI-SPEC Failure Mode).

EU AI Act transparency note (39-AI-SPEC.md Section 1b): the "AI-generated,
human-reviewed" labeling of narrative text in exported PDFs is a
`_render_narratives` rendering concern in `compliance_narrative_service.py`,
which this plan's must_haves lock as unchanged — no labeling behavior is
added here.

Uses `ainvoke` only — no bare `invoke`, no `asyncio.run`.
"""
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langgraph.checkpoint.memory import InMemorySaver
from opentelemetry import trace as _otel_trace
from pydantic import ValidationError

from ai_orchestration.decision_log import log_ai_decision
from ai_orchestration.guardrails import cross_tenant_output_scan, scan_input, scan_output
from ai_orchestration.memory import make_thread_id
from ai_orchestration.models import (
    ROUTER_STRUCTURED_OUTPUT_PASSTHROUGH,
    build_model_for_tenant,
    model_provenance,
)
from ai_orchestration.prompts import NARRATIVE_SYSTEM_PROMPT, PROMPT_VERSION
from ai_orchestration.schemas import NarrativeOutput
from ai_orchestration.tracing import attach_span_attributes
from ai_orchestration.validators import validate_framework_fidelity

logger = logging.getLogger(__name__)

_SURFACE = "narrative"
_EXECUTIVE_WORD_BUDGET = 150
_FRAMEWORK_WORD_BUDGET = 200

_UNSAFE = re.compile(r"[<>{}\[\]\\]")
_NEWLINES = re.compile(r"[\r\n]+")

_HANDLE_ERRORS_MSG = (
    "Output did not match the NarrativeOutput schema. Return `text` as plain "
    "prose within the requested word budget; no markdown, no headings."
)

# `NARRATIVE_SYSTEM_PROMPT` (prompts.py, 39-05) only covers the executive
# summary — the pre-39-09 service's per-framework findings narrative used a
# distinct system prompt (`generate_framework_narrative`'s `system_part`,
# lines 134-138 of the pre-migration `compliance_narrative_service.py`),
# never migrated into the shared `prompts.py` file. Preserved verbatim here
# (out of `prompts.py`'s file scope for this plan) rather than reusing the
# executive prompt for both call sites.
_FRAMEWORK_SYSTEM_PROMPT = (
    "You are a compliance analyst writing a findings narrative for a PDF report. "
    "Write factual, concise prose. Do not reference controls not listed below. "
    "Respond with narrative text only — no headings, no markdown."
)


@dataclass
class NarrativeResult:
    """Everything the `compliance_narrative_service.py` shim needs — the
    shim only reads `.text` (its public functions return plain `str`), but
    `.model_provenance`/`.fallback_used` are exposed for callers/tests that
    want provenance without re-deriving it."""

    text: str
    model_provenance: str
    fallback_used: bool


def _sanitise(value: str, max_len: int = 200) -> str:
    """Prompt-injection guard on interpolated control/framework names,
    preserved verbatim in intent from the pre-39-09 service: collapse
    embedded newlines first so a crafted name can't inject new
    "instruction" lines inside the <compliance_data> block, then strip
    characters that could otherwise break out of that block."""
    value = _NEWLINES.sub(" ", str(value))
    return _UNSAFE.sub("", value).strip()[:max_len]


def _raw_db(db: Any) -> Any:
    """Unwrap `TenantIsolatedDatabase` to the raw Motor db when present —
    mirrors `agents/auditor.py`/`agents/chat.py`/`agents/questionnaire.py`'s
    own unwrap for the same reason (non-exempt collections, e.g.
    `system_settings`, would otherwise get a tenantId filter injected that
    the acting tenant's settings lookup does not want)."""
    return getattr(db, "_db", db)


def _response_format():
    """Honor the 39-02/39-04 router structured-output passthrough decision:
    while `ROUTER_STRUCTURED_OUTPUT_PASSTHROUGH == "FAIL"`, always request
    structured output via `ToolStrategy` rather than a bare
    `response_format=NarrativeOutput` (AI-SPEC Section 4b)."""
    if ROUTER_STRUCTURED_OUTPUT_PASSTHROUGH == "FAIL":
        return ToolStrategy(NarrativeOutput, handle_errors=_HANDLE_ERRORS_MSG)
    return NarrativeOutput


def _fallback_executive_summary(framework: str, score: float) -> str:
    return (
        f"This report presents the {framework} compliance posture for the reporting period. "
        f"The overall compliance score is {score:.1f}%. "
        "Detailed findings are available in the per-framework section below. "
        "Please review the failing controls and engage your compliance team for remediation guidance."
    )


def _fallback_framework_narrative(framework: str, score: float) -> str:
    return (
        f"The {framework} framework scored {score:.1f}%. "
        "Detailed findings are available in the attached control table."
    )


async def _tenant_model_names(tenant_id: Optional[str], raw_db: Any) -> tuple:
    """Best-effort primary/fallback model name lookup, solely to compare
    against `response_metadata` via `model_provenance()`. Mirrors
    `agents/auditor.py::_tenant_model_names`. Degrades to (None, None) on
    any failure; provenance stamping must never block a narrative."""
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
    except Exception as exc:  # tracing must never block a narrative
        logger.debug("[ai_orchestration.agents.narrative] span attribute attach failed: %s", exc)


async def _record_decision(
    db: Any,
    ref: Dict[str, str],
    outcome: str,
    model_prov: str,
    fidelity_check: str,
    started_at: datetime,
) -> None:
    # log_ai_decision never re-raises (39-05 contract) — a decision-log
    # failure must never block a narrative.
    await log_ai_decision(
        db,
        _SURFACE,
        outcome=outcome,
        prompt_version=PROMPT_VERSION,
        model_provenance=model_prov,
        citation_validation=fidelity_check,
        ref=ref,
        started_at=started_at,
    )


async def _generate(
    *,
    kind: str,
    system_prompt: str,
    user_content: str,
    word_budget: int,
    fallback_text: str,
    tenant_id: Optional[str],
    db: Any,
    safe_fw: str,
) -> NarrativeResult:
    """Shared generation path for both `generate_executive` and
    `generate_framework` — every exit returns a `NarrativeResult` safe to
    render into a PDF; nothing here ever raises past this function."""
    started_at = datetime.now(timezone.utc)
    raw_db = _raw_db(db)
    ref = {"framework": safe_fw, "kind": kind}

    # --- Pre-invoke guardrail: PII/injection scan on the constructed prompt ---
    input_scan = await scan_input(user_content, _SURFACE)
    if not input_scan.passed:
        _attach_span(tenant_id, "primary")
        await _record_decision(db, ref, "input_guardrail_blocked", "primary", "n/a", started_at)
        return NarrativeResult(fallback_text, "primary", True)

    # --- Build + run the agent (no tools — narrative summarizes supplied data) ---
    try:
        model = await build_model_for_tenant(tenant_id, db, surface=_SURFACE)
        agent = create_agent(
            model=model,
            tools=[],
            system_prompt=system_prompt,
            response_format=_response_format(),
            checkpointer=InMemorySaver(),
        )
        thread_id = make_thread_id(tenant_id or "unknown", f"narrative:{kind}:{safe_fw}")
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": user_content}]},
            config={"configurable": {"thread_id": thread_id}, "recursion_limit": 10},
        )
    except Exception as exc:
        logger.error(
            "[ai_orchestration.agents.narrative] agent run failed kind=%s tenant=%s: %s",
            kind, tenant_id, exc,
        )
        _attach_span(tenant_id, "primary")
        await _record_decision(db, ref, "agent_invocation_error", "primary", "n/a", started_at)
        return NarrativeResult(fallback_text, "primary", True)

    structured = result.get("structured_response") if isinstance(result, dict) else None
    raw_text = getattr(structured, "text", None) if structured is not None else None
    if not raw_text:
        _attach_span(tenant_id, "primary")
        await _record_decision(db, ref, "no_structured_response", "primary", "n/a", started_at)
        return NarrativeResult(fallback_text, "primary", True)

    # --- Provenance ---
    messages = result.get("messages") if isinstance(result, dict) else None
    last_message = _last_message_with_metadata(messages)
    primary_name, fallback_name = await _tenant_model_names(tenant_id, raw_db)
    model_prov = model_provenance(last_message, primary_name, fallback_name)
    _attach_span(tenant_id, model_prov)

    # --- Word-budget + empty/BLOCKED/Error validation: recompute from the
    # actual returned text, never trust the model's self-reported
    # word_count/limit fields on the structured object itself. ---
    try:
        validated = NarrativeOutput.from_raw(raw_text, limit=word_budget)
    except ValidationError as exc:
        logger.warning(
            "[ai_orchestration.agents.narrative] validation failed kind=%s: %s", kind, exc
        )
        await _record_decision(db, ref, "validation_failed", model_prov, "n/a", started_at)
        return NarrativeResult(fallback_text, model_prov, True)

    # --- Post-invoke guardrails (output PII/injection + cross-tenant scan) ---
    output_scan = await scan_output(validated.text, _SURFACE)
    tenant_scan = await cross_tenant_output_scan(validated.text, tenant_id or "", raw_db)
    if not output_scan.passed or not tenant_scan.passed:
        await _record_decision(db, ref, "output_guardrail_blocked", model_prov, "n/a", started_at)
        return NarrativeResult(fallback_text, model_prov, True)

    # --- Framework-fidelity sweep (T-39-09-B): flag/downgrade any
    # control-ID-shaped token not present in the tenant's (+ global)
    # framework registry, fail-closed to the same deterministic fallback. ---
    fidelity = await validate_framework_fidelity(validated.text, tenant_id or "", raw_db)
    if not fidelity.ok:
        logger.warning(
            "[ai_orchestration.agents.narrative] framework-fidelity flag kind=%s: %s",
            kind, fidelity.detail,
        )
        await _record_decision(db, ref, "framework_fidelity_blocked", model_prov, "blocked", started_at)
        return NarrativeResult(fallback_text, model_prov, True)

    await _record_decision(db, ref, "generated", model_prov, "pass", started_at)
    return NarrativeResult(validated.text, model_prov, False)


async def generate_executive(
    framework_name: str,
    score: float,
    failing_controls: List[str],
    period: str,
    tenant_id: Optional[str],
    db: Any,
) -> NarrativeResult:
    """Generate the executive summary narrative (150-word budget) via
    `create_agent` + `NarrativeOutput`. Never raises."""
    safe_fw = _sanitise(framework_name)
    safe_controls = [_sanitise(c, 80) for c in failing_controls[:5]]
    controls_block = "\n".join(f"- {c}" for c in safe_controls) or "- None recorded"
    user_content = (
        f"<compliance_data>\nFramework: {safe_fw}\nCompliance score: {score:.1f}%\n"
        f"Reporting period: {period}\nTop failing controls:\n{controls_block}\n"
        f"</compliance_data>\n\nWrite an executive summary of no more than "
        f"{_EXECUTIVE_WORD_BUDGET} words."
    )
    return await _generate(
        kind="executive",
        system_prompt=NARRATIVE_SYSTEM_PROMPT,
        user_content=user_content,
        word_budget=_EXECUTIVE_WORD_BUDGET,
        fallback_text=_fallback_executive_summary(safe_fw, score),
        tenant_id=tenant_id,
        db=db,
        safe_fw=safe_fw,
    )


async def generate_framework(
    framework_name: str,
    score: float,
    failing_controls: List[str],
    remediation_summary: Any,
    tenant_id: Optional[str],
    db: Any,
) -> NarrativeResult:
    """Generate a per-framework findings narrative (200-word budget) via
    `create_agent` + `NarrativeOutput`. Never raises."""
    safe_fw = _sanitise(framework_name)
    safe_controls = [_sanitise(c, 80) for c in failing_controls[:7]]
    ctrl_block = "\n".join(f"- {c}" for c in safe_controls) or "- None recorded"
    safe_rem = _sanitise(str(remediation_summary or ""), 300) or "None provided"
    user_content = (
        f"<compliance_data>\nFramework: {safe_fw}\nScore: {score:.1f}%\n"
        f"Failing controls:\n{ctrl_block}\nRemediation notes: {safe_rem}\n"
        f"</compliance_data>\n\nWrite a findings narrative of no more than "
        f"{_FRAMEWORK_WORD_BUDGET} words."
    )
    return await _generate(
        kind="framework",
        system_prompt=_FRAMEWORK_SYSTEM_PROMPT,
        user_content=user_content,
        word_budget=_FRAMEWORK_WORD_BUDGET,
        fallback_text=_fallback_framework_narrative(safe_fw, score),
        tenant_id=tenant_id,
        db=db,
        safe_fw=safe_fw,
    )
