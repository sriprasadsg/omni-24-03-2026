"""LangChain OpenTelemetry instrumentation wiring for Phase 39 (AISPEC-39-S5/S7).

Adds `openinference-instrumentation-langchain` to the existing Arize Phoenix
pipeline `app_startup.py::init_agentic_tracing` builds for Anthropic calls,
so `create_agent` runs (tool calls, retries, fallback resolution) emit spans
alongside the existing Anthropic spans (39-RESEARCH.md Pitfall C: LangChain
calls are otherwise invisible to Phoenix — `AnthropicInstrumentor` only
patches the `anthropic` SDK, not `langchain_openai`/`langchain_ollama`).

`instrument_langchain` mirrors `init_agentic_tracing`'s own graceful-degrade
shape exactly: missing package -> log + continue, any other failure -> log
+ continue. It never raises, so a missing Phoenix process or missing
instrumentation package never blocks `run_startup_services()`.
"""
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Every LangChain-surface span must carry these four attributes
# (39-AI-SPEC.md Section 7) so `agent_ai_decisions` / audit-evidence review
# can walk from a sampled decision back to its trace.
REQUIRED_SPAN_ATTRIBUTES = ("tenant_id", "surface", "PROMPT_VERSION", "model_provenance")


def instrument_langchain(tracer_provider: Any) -> bool:
    """Instrument LangChain against an existing OTel tracer provider.

    Reuses the caller's already-built `TracerProvider`/OTLP exporter (the one
    `init_agentic_tracing` constructs for the Anthropic instrumentor) rather
    than standing up a second pipeline — one startup hook, not two with
    different failure semantics. Returns True on success, False on any
    degrade (ImportError or otherwise); never raises.
    """
    try:
        from openinference.instrumentation.langchain import LangChainInstrumentor

        LangChainInstrumentor().instrument(tracer_provider=tracer_provider)
        logger.info("[ai_orchestration.tracing] LangChain instrumentation active")
        return True
    except ImportError:
        logger.warning(
            "[ai_orchestration.tracing] openinference-instrumentation-langchain not "
            "installed — LangChain agent calls will not be traced. Run: pip install "
            "openinference-instrumentation-langchain"
        )
        return False
    except Exception as exc:
        logger.warning("[ai_orchestration.tracing] Failed to instrument LangChain: %s", exc)
        return False


def attach_span_attributes(
    span: Any,
    *,
    tenant_id: Optional[str],
    surface: str,
    prompt_version: str,
    model_provenance: str,
) -> None:
    """Attach the four mandatory span attributes (39-AI-SPEC.md Section 7).

    Callers own the span lifecycle (typically `trace.get_current_span()`
    inside an `ainvoke` pre/post hook in an agent surface) — this helper only
    sets attributes on an already-live span object exposing `set_attribute`;
    it never creates, starts, or ends a span.
    """
    span.set_attribute("tenant_id", tenant_id or "")
    span.set_attribute("surface", surface)
    span.set_attribute("PROMPT_VERSION", prompt_version)
    span.set_attribute("model_provenance", model_provenance)
