"""OpenTelemetry tracing helpers for LangChain instrumented agents (39-07).

Exposes `attach_span_attributes` used by every surface and the
`instrument_langchain` wrapper that registers the OpenInference
langchain instrumentor against the existing Phoenix tracer provider.
"""
import logging

logger = logging.getLogger(__name__)


def attach_span_attributes(span, **attrs) -> None:
    """Attach a flat dict of string/string-keyed attributes to an OTel span.

    Used by all surfaces (auditor/chat/questionnaire/narrative) to stamp
    tenant_id, surface, prompt_version, model_provenance (primary|fallback),
    structured_output_valid (bool), and citation_validation (pass|blocked).

    Never raises — tracing must not block an AI evaluation or degrade a
    tenant-facing response.
    """
    if span is None:
        return
    for key, value in attrs.items():
        try:
            span.set_attribute(key, value if not isinstance(value, bool) else str(value))
        except Exception as exc:  # pragma: no cover — defensive
            logger.debug("[tracing] set_attribute %s failed: %s", key, exc)


def instrument_langchain(tracer_provider=None) -> bool:
    """Register the OpenInference LangChain instrumentor on `tracer_provider`.

    Returns True if instrumentation succeeded, False if the optional
    `openinference.instrumentation.langchain` package is not installed or
    instrument() raised (graceful degrade — LangChain traces simply won't
    appear in Phoenix, but the app keeps running).

    Call once at startup alongside the existing Anthropic instrumentor in
    `app_startup.py::_setup_agentic_tracing`.
    """
    try:
        from openinference.instrumentation.langchain import LangChainInstrumentor
        LangChainInstrumentor().instrument(tracer_provider=tracer_provider)
        logger.info("[tracing] LangChain instrumentor registered")
        return True
    except ImportError:
        logger.debug("[tracing] openinference.langchain not installed; skipping")
        return False
    except Exception as exc:
        logger.warning("[tracing] LangChain instrumentor failed: %s", exc)
        return False
