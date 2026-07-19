"""Per-tenant LangChain model factory for Phase 39 AI surfaces (AISPEC-39-S4).

Reads the exact same `system_settings` document
(`{"type": "llm", "tenantId": tenant_id}`) that
`ai_service.IncidentAnalyzer.get_provider_for_tenant` reads today, so
per-tenant provider configuration (router/9router, Ollama, Anthropic,
Gemini) keeps working identically for every new LangChain surface
(auditor, chat, questionnaire, narrative — 39-06 through 39-09).

Tenant provider caching/invalidation is owned exclusively by `ai_service`'s
existing internal per-tenant provider cache (see `ai_service.py`).
This module intentionally does NOT maintain a second, independent
per-tenant provider cache (39-RESEARCH.md Anti-Pattern: "Duplicating the
provider-settings cache"); `invalidate_tenant_model_cache` below is a thin
delegate to `ai_service.invalidate_tenant_provider` so there is exactly one
cache-eviction path for both the legacy providers and this factory.

`tenant_id` is used ONLY to look up settings here — it must never be
passed through as a tool-facing or model-facing argument to an LLM
(RESEARCH.md Pitfall B / 39-AI-SPEC.md Pitfall 3).
"""
import logging
import os
from typing import Any, Optional

from langchain.chat_models import init_chat_model

from ai_service import ai_service
from local_ip import ollama_default_url

logger = logging.getLogger(__name__)

# 39-02's live 9router `create_agent(response_format=..., tools=[...])`
# passthrough smoke test recorded UNRESOLVED-IN-THIS-SANDBOX (no live
# AI_ROUTER_URL access) and, per that plan's own context_notes, is treated
# conservatively as FAIL until re-run with live gateway access confirms a
# PASS (see 39-02-SUMMARY.md "Decisions Made"). This factory still builds
# the router-backed primary model below for plain generation (the same
# route `ai_service.OpenAICompatProvider` already uses successfully today);
# what remains unverified is *structured output / tool-calling* passed
# through the router. Agent-surface plans (39-06..39-09) needing
# `response_format=`/tool-calling MUST NOT assume that passes through the
# router unmodified — prefer `ToolStrategy` or a direct `anthropic`
# provider model (see `_build_anthropic_model` below) until re-verified.
ROUTER_STRUCTURED_OUTPUT_PASSTHROUGH = "FAIL"

_ROUTER_PROVIDER_VALUES = {"router", "9router", "openai_compat", "openai-compatible"}
_OLLAMA_PROVIDER_VALUES = {"ollama", "Ollama (Local)", "Local"}
_ANTHROPIC_PROVIDER_VALUES = {"anthropic", "claude", "Anthropic Claude"}
_GEMINI_PROVIDER_VALUES = {"gemini", "Gemini"}

# Per-surface generation params (39-AI-SPEC.md Section 4 Model Configuration table).
_SURFACE_PARAMS = {
    "auditor": {"temperature": 0.1, "max_tokens": 4096},
    "narrative": {"temperature": 0.1, "max_tokens": 4096},
    "chat": {"temperature": 0.3, "max_tokens": 2048},
    "questionnaire": {"temperature": 0.0, "max_tokens": 1024},
    "supervisor": {"temperature": 0.0, "max_tokens": 512},
}
_DEFAULT_SURFACE_PARAMS = {"temperature": 0.1, "max_tokens": 1024}


def _build_local_ollama_model(settings: dict, **overrides: Any):
    """Build the local Ollama fallback model — never tenant-mutable, always local."""
    base_url = (
        settings.get("ollamaUrl")
        or settings.get("ollama_url")
        or os.getenv("OLLAMA_URL")
        or ollama_default_url()
    )
    model_name = (
        settings.get("ollamaModel")
        or os.getenv("OLLAMA_MODEL", os.getenv("LLM_MODEL", "llama3.2:3b"))
    )
    return init_chat_model(
        model=model_name,
        model_provider="ollama",
        base_url=base_url,
        temperature=overrides.get("temperature", 0.1),
    )


def _build_router_model(settings: dict, **overrides: Any):
    """Build the primary model via the 9router gateway (OpenAI-compatible wire format)."""
    base_url = (
        settings.get("routerUrl")
        or settings.get("baseUrl")
        or os.getenv("AI_ROUTER_URL")
        or ""
    ).rstrip("/")
    # The OpenAI-compatible client appends only "/chat/completions" to base_url,
    # so base_url MUST already carry the "/v1" API prefix. AI_ROUTER_URL is
    # configured without it — the legacy ai_providers.OpenAICompatProvider
    # appended "/v1/chat/completions" by hand. Mirror that here, or the client
    # hits "/chat/completions" (no /v1), which the gateway serves as a 404 HTML
    # page and surfaces as the "router_returned_html" chain failure.
    if base_url and not base_url.endswith("/v1"):
        base_url = f"{base_url}/v1"
    api_key = settings.get("apiKey") or os.getenv("AI_ROUTER_KEY") or ""
    model_name = settings.get("model") or os.getenv("AI_ROUTER_MODEL") or "claude-sonnet-4-6"
    if not (base_url and api_key and model_name):
        raise ValueError("router settings incomplete: base_url/api_key/model all required")
    params = dict(overrides)
    timeout = params.pop("timeout", 60)
    max_retries = params.pop("max_retries", 3)
    return init_chat_model(
        model=model_name,
        model_provider="openai",
        base_url=base_url,
        api_key=api_key,
        timeout=timeout,
        max_retries=max_retries,
        **params,
    )


def _build_anthropic_model(settings: dict, **overrides: Any):
    """Build the primary model via native langchain-anthropic.

    When `ANTHROPIC_BASE_URL` is set it points the Anthropic Messages API at
    that gateway (the same host the OpenAI-compat router uses here), so this
    reaches Claude over `/v1/messages` — whose NATIVE tool-calling is reliable,
    unlike the OpenAI-compat `/v1/chat/completions` tool passthrough that
    ROUTER_STRUCTURED_OUTPUT_PASSTHROUGH flags. Without it, this hits the real
    Anthropic API."""
    api_key = settings.get("apiKey") or settings.get("anthropicApiKey") or os.getenv("ANTHROPIC_API_KEY")
    model_name = settings.get("model") or os.getenv("LLM_MODEL", "claude-sonnet-4-6")
    if not api_key:
        raise ValueError("anthropic settings incomplete: apiKey required")
    kwargs = dict(overrides)
    base_url = os.getenv("ANTHROPIC_BASE_URL")
    if base_url:
        kwargs["base_url"] = base_url.rstrip("/")
    return init_chat_model(
        model=model_name,
        model_provider="anthropic",
        api_key=api_key,
        **kwargs,
    )


def _build_router_structured_bypass(settings: dict, **overrides: Any):
    """For a router tenant on a surface that needs tool-calling: reach Claude via
    the Anthropic Messages API on the same gateway instead of the OpenAI-compat
    chat-completions endpoint, sidestepping the unverified structured-output
    passthrough (ROUTER_STRUCTURED_OUTPUT_PASSTHROUGH). Reuses the router's own
    key/model. Raises if neither an Anthropic base URL nor key is available so
    the caller can fall back to the plain router model."""
    if not os.getenv("ANTHROPIC_BASE_URL"):
        raise ValueError("no ANTHROPIC_BASE_URL for structured-output bypass")
    bypass_settings = dict(settings)
    bypass_settings["apiKey"] = (
        settings.get("apiKey") or os.getenv("ANTHROPIC_API_KEY") or os.getenv("AI_ROUTER_KEY")
    )
    bypass_settings["model"] = (
        settings.get("model") or os.getenv("AI_ROUTER_MODEL") or os.getenv("LLM_MODEL", "claude-sonnet-4-6")
    )
    return _build_anthropic_model(bypass_settings, **overrides)


def _build_gemini_model(settings: dict, **overrides: Any):
    """Build the primary model via Gemini, if the tenant's settings request it."""
    api_key = settings.get("apiKey") or os.getenv("GEMINI_API_KEY")
    model_name = settings.get("model") or os.getenv("LLM_MODEL", "gemini-2.0-flash")
    if not api_key:
        raise ValueError("gemini settings incomplete: apiKey required")
    return init_chat_model(
        model=model_name,
        model_provider="google_genai",
        api_key=api_key,
        **overrides,
    )


def _build_primary_model(
    configured_provider: str, settings: dict, structured_output: bool = False, **overrides: Any
):
    """Dispatch to the right provider builder from the settings.provider string.

    Maps the same provider string values `ai_service._create_provider_from_settings`
    already maps (39-PATTERNS.md): router/9router/openai_compat/openai-compatible,
    ollama, anthropic/claude, gemini. Unknown/unset providers default to the
    router, matching `ai_service.IncidentAnalyzer.initialize()`'s own default
    preference order.

    `structured_output=True` marks a surface that needs tool-calling. For a
    router tenant, that OpenAI-compat passthrough is unverified
    (ROUTER_STRUCTURED_OUTPUT_PASSTHROUGH); when it isn't confirmed PASS this
    reaches Claude via the Anthropic Messages API on the same gateway instead,
    falling back to the plain router model if that bypass can't be built.
    """
    if configured_provider in _OLLAMA_PROVIDER_VALUES:
        return _build_local_ollama_model(settings, **overrides)
    if configured_provider in _ANTHROPIC_PROVIDER_VALUES:
        return _build_anthropic_model(settings, **overrides)
    if configured_provider in _GEMINI_PROVIDER_VALUES:
        return _build_gemini_model(settings, **overrides)
    # _ROUTER_PROVIDER_VALUES and anything else (unset/unrecognized) -> router.
    if structured_output and ROUTER_STRUCTURED_OUTPUT_PASSTHROUGH != "PASS":
        try:
            model = _build_router_structured_bypass(settings, **overrides)
            logger.info(
                "[ai_orchestration.models] structured-output surface on router tenant — "
                "using Anthropic Messages API bypass (ROUTER_STRUCTURED_OUTPUT_PASSTHROUGH=%s)",
                ROUTER_STRUCTURED_OUTPUT_PASSTHROUGH,
            )
            return model
        except Exception as exc:
            logger.warning(
                "[ai_orchestration.models] structured-output bypass unavailable (%s) — "
                "using plain router model; tool-calling passthrough is unverified.", exc,
            )
    return _build_router_model(settings, **overrides)


# Surfaces that request structured output / tool-calling (create_agent +
# ToolStrategy/response_format) — these need the tool-calling-capable path on a
# router tenant. `chat` is free-text and stays on the plain router.
_STRUCTURED_SURFACES = {"auditor", "questionnaire", "narrative", "supervisor"}


async def build_model_for_tenant(
    tenant_id: Optional[str], db, surface: str = "chat", structured_output: Optional[bool] = None
):
    """Build a per-tenant primary model wrapped in a local-Ollama fallback chain.

    Reads `db.system_settings.find_one({"type": "llm", "tenantId": tenant_id})` —
    the exact document `ai_service.get_provider_for_tenant` reads — and returns
    `primary.with_fallbacks([local_ollama])` so gateway/API failures degrade to
    the local model instead of a 500 (39-AI-SPEC.md Section 4 Core Pattern).

    `surface` selects the per-surface generation params (auditor/narrative:
    temperature=0.1 max_tokens=4096; chat: temperature=0.3 max_tokens=2048;
    questionnaire: temperature=0.0 max_tokens=1024). `structured_output`
    overrides the surface-derived default for whether tool-calling is needed
    (auditor/questionnaire/narrative/supervisor default True) — see
    `_build_primary_model` for the router bypass this drives.
    """
    overrides = dict(_SURFACE_PARAMS.get(surface, _DEFAULT_SURFACE_PARAMS))
    if structured_output is None:
        structured_output = surface in _STRUCTURED_SURFACES
    raw = db._db if hasattr(db, "_db") else db
    settings = None
    if tenant_id:
        settings = await raw.system_settings.find_one({"type": "llm", "tenantId": tenant_id})
    settings = settings or {}
    configured_provider = settings.get("provider", "")

    try:
        primary = _build_primary_model(
            configured_provider, settings, structured_output=structured_output, **overrides
        )
    except Exception as exc:
        logger.warning(
            "[ai_orchestration.models] Primary model build failed for tenant=%s "
            "provider=%s surface=%s: %s — falling back to local Ollama as primary.",
            tenant_id, configured_provider, surface, exc,
        )
        primary = _build_local_ollama_model(settings, **overrides)

    local = _build_local_ollama_model(settings, temperature=overrides.get("temperature", 0.1))
    return primary.with_fallbacks([local])


def invalidate_tenant_model_cache(tenant_id: Optional[str]) -> None:
    """Evict this tenant's cached provider so the next lookup re-reads settings.

    Delegates entirely to the existing `ai_service` cache-eviction method —
    call this (or `ai_service.invalidate_tenant_provider` directly) whenever a
    tenant's `system_settings` "llm" document changes.
    """
    ai_service.invalidate_tenant_provider(tenant_id)


# Bump when the model-routing logic changes — the diagnostics endpoint returns
# this so an operator can confirm a restart actually loaded the new code.
MODELS_REVISION = "2026-07-19-router-v1-anthropic-bypass"


def _describe_model(model: Any) -> dict:
    """Provider class + resolved base_url + model name for one built model.
    Never includes the API key. Used only by diagnostics."""
    base_url = None
    for attr in ("anthropic_api_url", "openai_api_base", "base_url"):
        val = getattr(model, attr, None)
        if val:
            base_url = str(val)
            break
    if base_url is None:
        client = getattr(model, "_client", None) or getattr(model, "async_client", None)
        if client is not None:
            base_url = str(getattr(getattr(client, "_client", client), "base_url", "")) or None
    return {
        "class": type(model).__name__,
        "base_url": base_url,
        "model": getattr(model, "model", None) or getattr(model, "model_name", None),
    }


async def describe_model_for_tenant(tenant_id: Optional[str], db, surface: str = "chat") -> dict:
    """Resolve (but never invoke) the model a surface would use, for diagnostics.

    Builds the same chain `build_model_for_tenant` would and introspects the
    primary — no network call is made. Reports whether the Anthropic-Messages
    structured-output bypass is the active primary path for this surface."""
    structured = surface in _STRUCTURED_SURFACES
    chain = await build_model_for_tenant(tenant_id, db, surface=surface)
    primary = getattr(chain, "runnable", None) or chain  # unwrap .with_fallbacks
    desc = _describe_model(primary)
    desc.update({
        "surface": surface,
        "structured_output": structured,
        "anthropic_bypass_active": structured and desc["class"] == "ChatAnthropic",
    })
    return desc


def fallback_ollama_url() -> str:
    """The local Ollama URL the fallback chain degrades to — for loud logging
    when the whole primary+fallback chain is exhausted."""
    return os.getenv("OLLAMA_URL") or ollama_default_url()


def classify_chain_failure(exc: Exception) -> tuple:
    """Classify an exhausted primary+fallback model-chain failure for a loud,
    actionable log. `.with_fallbacks([local])` raises only the PRIMARY's error
    once every model is exhausted, so this runs only when BOTH the router model
    and the local Ollama fallback have already failed. Returns
    (short_reason, one_line_detail) — never the raw multi-KB body."""
    text = str(exc)
    low = text.lower()
    if "<!doctype html" in low or "_next/" in low or "<html" in low:
        # The router base_url answered with a web page, not the /v1 JSON API —
        # AI_ROUTER_URL points at the gateway's UI, or the gateway is down and a
        # front proxy is serving a placeholder.
        return "router_returned_html", "router endpoint served an HTML page, not the /v1 JSON API"
    if "connection refused" in low or "timed out" in low or "timeout" in low or "connect" in low:
        return "chain_unreachable", text.split("\n", 1)[0][:200]
    return "agent_invocation_error", text.split("\n", 1)[0][:200]


def model_provenance(
    response: Any,
    primary_model_name: Optional[str] = None,
    fallback_model_name: Optional[str] = None,
) -> str:
    """Return "primary" or "fallback:<model>" for a model response.

    `.with_fallbacks([...])` resolves silently on failure — the returned
    message carries which model actually produced it via
    `response_metadata` (key name varies by provider: `model_name`/`model`/
    `model_id`). Agents should stamp their structured output's
    `model_provenance` field with this helper's return value so a degraded
    (fallback) finding is never presented identically to a primary-model one
    (39-AI-SPEC.md Failure Mode 5).
    """
    metadata = getattr(response, "response_metadata", None) or {}
    used_model = (
        metadata.get("model_name")
        or metadata.get("model")
        or metadata.get("model_id")
        or ""
    )
    if fallback_model_name and used_model and (
        used_model == fallback_model_name
        or fallback_model_name in used_model
        or used_model in fallback_model_name
    ):
        return f"fallback:{used_model}"
    if used_model and primary_model_name and not (
        used_model == primary_model_name
        or primary_model_name in used_model
        or used_model in primary_model_name
    ):
        # Resolved model doesn't match the known primary -> treat as fallback,
        # even if the caller didn't pass an explicit fallback_model_name.
        return f"fallback:{used_model}"
    return "primary"
