"""Model factory for LangChain agents (39-04).

Builds primary model via OpenAI-compatible gateway (9router) with
Ollama local fallback. Reads tenant system_settings for per-tenant config.
"""
import logging
import os

logger = logging.getLogger(__name__)

ROUTER_STRUCTURED_OUTPUT_PASSTHROUGH = "FAIL"


def fallback_ollama_url() -> str:
    return os.getenv("OLLAMA_URL", "http://localhost:11434")


def model_provenance(last_message, primary_name, fallback_name) -> str:
    if not last_message:
        return "primary"
    meta = getattr(last_message, "response_metadata", None)
    if meta:
        model_name = meta.get("model_name") or meta.get("model", "")
        if fallback_name and fallback_name in str(model_name):
            return "fallback"
    return "primary"


def classify_chain_failure(exc) -> tuple:
    exc_str = str(exc).lower()
    if "timeout" in exc_str or "timed out" in exc_str:
        return "timeout", str(exc)[:300]
    if "rate" in exc_str and "limit" in exc_str:
        return "rate_limited", str(exc)[:300]
    if "connection" in exc_str or "connect" in exc_str:
        return "connection_error", str(exc)[:300]
    return "unknown_error", str(exc)[:300]


async def build_model_for_tenant(tenant_id: str, db, surface: str = "default"):
    """Build a LangChain ChatModel for the given tenant.

    Primary: OpenAI-compatible endpoint (9router gateway).
    Fallback: local Ollama.
    Returns primary.with_fallbacks([local]).
    """
    try:
        from langchain.chat_models import init_chat_model
    except ImportError:
        logger.error("langchain not installed; cannot build model")
        return None

    primary_url = os.getenv("AI_ROUTER_URL", "http://localhost:8080")
    primary_key = os.getenv("AI_ROUTER_KEY", "")
    primary_model = os.getenv("AI_ROUTER_MODEL", "claude-sonnet-4-6")

    # Try tenant-specific settings
    if tenant_id and db:
        try:
            raw = getattr(db, "_db", db)
            settings = await raw.system_settings.find_one({"type": "llm", "tenantId": tenant_id})
            if settings:
                primary_url = settings.get("routerUrl", primary_url)
                primary_key = settings.get("apiKey", primary_key)
                primary_model = settings.get("model", primary_model)
        except Exception:
            pass

    primary = init_chat_model(
        model=primary_model,
        model_provider="openai",
        base_url=primary_url,
        api_key=primary_key,
        temperature=0.1,
        max_tokens=4096,
    )

    ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    local = init_chat_model(
        model=f"ollama:{ollama_model}",
        base_url=fallback_ollama_url(),
        temperature=0.1,
    )

    return primary.with_fallbacks([local])
