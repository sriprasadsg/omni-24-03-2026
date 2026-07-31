"""Multi-agent supervisor — routes a free-form request to the right surface.

The four Phase-39 agent surfaces (auditor, chat, questionnaire, narrative) each
run in isolation, invoked directly by their own endpoints with structured
inputs. This supervisor adds the missing routing/handoff layer: given a natural
-language request, it classifies intent via `create_agent` structured output
(`RoutingDecision`) and dispatches to the chosen surface — the one PraisonAI
capability the gap analysis flagged as genuinely absent.

Fail-closed and degrade-safe, mirroring every other surface here:
  * Guardrail-blocked input never reaches a model — returns a safe chat-shaped
    result marked blocked.
  * A structured surface (auditor/narrative) is only invoked when ALL of its
    required inputs are actually present (from the request or a caller-supplied
    `context`); otherwise the supervisor degrades to `chat` and records it,
    rather than calling a surface with missing data.
  * A router-model failure (whole primary+fallback chain exhausted) degrades to
    `chat`, logged loudly via `classify_chain_failure` like the other agents.

`context` lets a caller that already holds structured data (evidence text, a
compliance score, failing controls) enable a real auditor/narrative handoff;
caller-supplied context always wins over the model's best-effort extraction.
"""
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langgraph.checkpoint.memory import InMemorySaver
from opentelemetry import trace as _otel_trace

from ai_orchestration.agents.auditor import evaluate_control
from ai_orchestration.agents.chat import chat
from ai_orchestration.agents.narrative import generate_executive
from ai_orchestration.agents.questionnaire import generate_draft
from ai_orchestration.decision_log import log_ai_decision
from ai_orchestration.guardrails import scan_input
from ai_orchestration.memory import make_thread_id
from ai_orchestration.models import (
    build_model_for_tenant,
    classify_chain_failure,
    fallback_ollama_url,
)
from ai_orchestration.prompts import PROMPT_VERSION, SUPERVISOR_SYSTEM_PROMPT
from ai_orchestration.schemas import RoutingDecision
from ai_orchestration.tracing import attach_span_attributes

logger = logging.getLogger("ai_orchestration.agents.supervisor")

_SURFACE = "supervisor"


@dataclass
class SupervisorResult:
    """Unified return for a routed request.

    `routed_to` is the surface the router chose; `surface` is the surface
    actually invoked — they differ when a structured surface lacked its
    required inputs and the supervisor degraded to `chat` (`degraded=True`).
    `result` is the underlying surface's own native return value."""

    surface: str
    routed_to: str
    reason: str
    result: Any
    degraded: bool = False
    blocked: bool = False
    extracted: dict = field(default_factory=dict)


def _raw_db(db: Any) -> Any:
    """Unwrap TenantIsolatedDatabase to the raw Motor db — mirrors the other
    agent modules (see agents/auditor.py::_raw_db)."""
    return getattr(db, "_db", db)


def _attach_span(tenant_id: Optional[str], routed_to: str) -> None:
    try:
        span = _otel_trace.get_current_span()
        attach_span_attributes(
            span,
            tenant_id=tenant_id,
            surface=_SURFACE,
            prompt_version=PROMPT_VERSION,
            model_provenance="primary",
        )
        span.set_attribute("gen_ai.supervisor.routed_to", routed_to)
    except Exception as exc:  # tracing must never block a routed request
        logger.debug("[supervisor] span attribute attach failed: %s", exc)


async def _record_decision(
    db: Any, routed_to: str, outcome: str, started_at: datetime
) -> None:
    await log_ai_decision(
        db,
        _SURFACE,
        outcome=outcome,
        prompt_version=PROMPT_VERSION,
        model_provenance="primary",
        ref={"routed_to": routed_to},
        started_at=started_at,
    )


async def _classify(query: str, tenant_id: Optional[str], db: Any) -> RoutingDecision:
    """Run the routing classifier. Raises on a fully-exhausted model chain —
    the caller degrades to chat."""
    model = await build_model_for_tenant(tenant_id, db, surface=_SURFACE)
    agent = create_agent(
        model=model,
        tools=[],
        system_prompt=SUPERVISOR_SYSTEM_PROMPT,
        response_format=ToolStrategy(RoutingDecision),
        checkpointer=InMemorySaver(),
    )
    thread_id = make_thread_id(tenant_id or "unknown", f"route:{uuid.uuid4().hex[:8]}")
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": query}]},
        config={"configurable": {"thread_id": thread_id}, "recursion_limit": 8},
    )
    decision = result.get("structured_response") if isinstance(result, dict) else None
    if decision is None:
        # No structured response — treat as "route to chat", the safe default.
        return RoutingDecision(surface="chat", reason="no structured routing response")
    return decision


async def route_request(
    query: str,
    tenant_id: str,
    db: Any = None,
    history: Optional[list[dict[str, str]]] = None,
    context: Optional[dict] = None,
) -> SupervisorResult:
    """Route a free-form request to the right agent surface and invoke it.

    Always returns a `SupervisorResult` — guardrail blocks, router failures,
    and structured-surface input gaps are all resolved to a safe `chat`-shaped
    outcome before returning; callers never see a raw exception."""
    started_at = datetime.now(timezone.utc)
    if db is None:
        from database import get_database
        db = get_database()
    ctx = dict(context or {})

    # --- Pre-invoke guardrail on the raw user request ---
    input_scan = await scan_input(query, _SURFACE)
    if not input_scan.passed:
        _attach_span(tenant_id, "blocked")
        await _record_decision(db, "blocked", "blocked", started_at)
        return SupervisorResult(
            surface="chat",
            routed_to="blocked",
            reason="input_guardrail_blocked: " + "; ".join(input_scan.findings),
            result={"answer": "That request could not be processed.", "sources": []},
            blocked=True,
        )

    # --- Route ---
    try:
        decision = await _classify(query, tenant_id, db)
    except Exception as exc:
        reason, detail = classify_chain_failure(exc)
        logger.error(
            "[supervisor] MODEL CHAIN EXHAUSTED (routing) — primary AND local Ollama "
            "fallback both failed. tenant=%s reason=%s fallback=%s detail=%s — "
            "degrading route to chat.",
            tenant_id, reason, fallback_ollama_url(), detail,
        )
        decision = RoutingDecision(surface="chat", reason=f"router_failed:{reason}")

    routed_to = decision.surface
    extracted = {
        "framework_name": decision.framework_name,
        "control_desc": decision.control_desc,
        "question_text": decision.question_text,
    }
    _attach_span(tenant_id, routed_to)

    # Caller-supplied context wins over model extraction for the structured surfaces.
    framework_name = ctx.get("framework_name") or decision.framework_name
    control_desc = ctx.get("control_desc") or decision.control_desc
    evidence_text = ctx.get("evidence_text")
    score = ctx.get("score")

    async def _degrade_to_chat(why: str) -> SupervisorResult:
        chat_result = await chat(query, tenant_id, history, db=db)
        await _record_decision(db, routed_to, "degraded:chat", started_at)
        return SupervisorResult(
            surface="chat", routed_to=routed_to, reason=why,
            result=chat_result, degraded=True, extracted=extracted,
        )

    # --- Dispatch ---
    if routed_to == "auditor":
        if not (framework_name and control_desc and evidence_text):
            return await _degrade_to_chat(
                "auditor needs framework + control + evidence; missing here, answered via chat"
            )
        result = await evaluate_control(
            framework_name=framework_name, control_desc=control_desc,
            evidence_text=evidence_text, tenant_id=tenant_id, db=db,
            control_id=ctx.get("control_id"),
        )
        await _record_decision(db, routed_to, "auditor", started_at)
        return SupervisorResult("auditor", routed_to, decision.reason, result, extracted=extracted)

    if routed_to == "narrative":
        if not (framework_name and score is not None):
            return await _degrade_to_chat(
                "narrative needs a framework + compliance score; missing here, answered via chat"
            )
        result = await generate_executive(
            framework_name=framework_name, score=float(score),
            failing_controls=ctx.get("failing_controls", []),
            period=ctx.get("period", "current"), tenant_id=tenant_id, db=db,
        )
        await _record_decision(db, routed_to, "narrative", started_at)
        return SupervisorResult("narrative", routed_to, decision.reason, result, extracted=extracted)

    if routed_to == "questionnaire":
        question_text = decision.question_text or ctx.get("question_text") or query
        result = await generate_draft(
            question_id=ctx.get("question_id") or f"adhoc-{uuid.uuid4().hex[:8]}",
            question_text=question_text, tenant_id=tenant_id, db=db,
            question_set_id=ctx.get("question_set_id"),
        )
        await _record_decision(db, routed_to, "questionnaire", started_at)
        return SupervisorResult("questionnaire", routed_to, decision.reason, result, extracted=extracted)

    # chat (explicit route, or the default)
    result = await chat(query, tenant_id, history, db=db)
    await _record_decision(db, "chat", "chat", started_at)
    return SupervisorResult("chat", "chat", decision.reason, result, extracted=extracted)
