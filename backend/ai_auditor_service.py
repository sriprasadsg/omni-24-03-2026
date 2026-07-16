"""Compliance AI Auditor.

Evaluates collected evidence against a control requirement and returns a
PASS/FAIL verdict plus a one-sentence reason. Routes through the shared
`ai_service`, which is configured to a LOCAL provider by default
(OmniLocalProvider, then Ollama) — no external API calls, no hardcoded toy
model. Previously this loaded HuggingFaceTB/SmolLM-135M directly (and crashed on
a missing `os` import), so evaluations always returned "AI Model failed to load".
"""

import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger("ai_auditor")

# Preferred local instruct models, in order, when the operator hasn't pinned one
# via AI_AUDITOR_MODEL. Matched as a prefix against whatever Ollama has pulled.
_PREFERRED_MODELS = ["llama3.2", "llama3", "qwen2.5", "gemma", "qwen3", "mistral", "phi"]


async def _local_ollama_provider():
    """Build a LOCAL Ollama provider bound to an actually-available model.

    The global AI setting on this deployment points at a model that isn't pulled
    ("SecurityExpert:latest"), which silently degrades every AI feature to the
    Mock provider. The compliance auditor must not depend on that: it selects a
    real local model from whatever Ollama has, so audits run on a genuine local
    LLM regardless of the global misconfiguration.
    """
    try:
        import httpx
        from ai_providers import OllamaProvider
        from local_ip import ollama_default_url

        base_url = os.getenv("OLLAMA_URL") or ollama_default_url()
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base_url.rstrip('/')}/api/tags")
            available = [m.get("name", "") for m in resp.json().get("models", [])]
        if not available:
            return None

        pinned = os.getenv("AI_AUDITOR_MODEL")
        chosen: Optional[str] = None
        if pinned and any(pinned in a or a.startswith(pinned.split(":")[0]) for a in available):
            chosen = pinned
        else:
            for pref in _PREFERRED_MODELS:
                match = next((a for a in available if a.startswith(pref)), None)
                if match:
                    chosen = match
                    break
            chosen = chosen or available[0]

        # Set fields directly rather than calling configure(): configure() does a
        # warmup test-generate that times out while a cold model loads on first
        # use, wrongly reporting it unavailable. We already confirmed the model is
        # in /api/tags above, so bind it and let the real audit call load it.
        provider = OllamaProvider()
        provider.base_url = base_url
        provider.model_name = chosen
        logger.info("[AI AUDITOR] Using local Ollama model '%s'", chosen)
        return provider
    except Exception as e:
        logger.warning("[AI AUDITOR] Local Ollama provider unavailable: %s", e)
    return None

_SYSTEM = (
    "You are a strict technical auditor. Evaluate the evidence against the control "
    "requirement. Base your answer ONLY on the provided evidence; do not assume "
    "anything not present. Respond with EXACTLY two lines:\n"
    "VERDICT: PASS   (or)   VERDICT: FAIL\n"
    "REASONING: <one concise sentence explaining the verdict>"
)


class LocalAIAuditor:
    """Thin async wrapper over the shared local AI provider."""

    def __init__(self) -> None:
        # Filled in after the first evaluation so callers can record which model
        # produced the verdict (the concrete provider is chosen by ai_service).
        self.model_id = "local-ai"

    async def evaluate_evidence(
        self, framework_name: str, control_desc: str, evidence_text: str
    ) -> Dict[str, Any]:
        from ai_service import ai_service

        now = datetime.now(timezone.utc).isoformat()
        prompt = (
            f"{_SYSTEM}\n\n"
            f"Framework: {framework_name}\n"
            f"Requirement: {control_desc}\n"
            f"Evidence:\n{evidence_text[:1500]}"
        )

        try:
            # Prefer the configured provider (e.g. the 9router gateway → a strong
            # model like claude-sonnet-5). Fall back to a guaranteed-local Ollama
            # model only when nothing real is configured (Mock/unavailable).
            if not ai_service.is_configured:
                await ai_service.initialize()
            provider = getattr(ai_service, "provider", None)
            if provider is None or provider.__class__.__name__ == "MockProvider":
                local = await _local_ollama_provider()
                if local is not None:
                    provider = local

            self.model_id = (
                getattr(provider, "model_name", None)
                or (provider.__class__.__name__ if provider else "local-ai")
            )
            raw = await ai_service.generate_text(prompt, source="ai_auditor", provider=provider)
        except Exception as e:
            logger.error("AI auditor inference failed: %s", e)
            return {
                "verified": False,
                "reasoning": f"Local AI inference error: {e}",
                "evaluatedAt": now,
            }

        raw = (raw or "").strip()
        # A guardrail block or empty response is a non-verdict — fail closed.
        if not raw or raw.startswith("BLOCKED:"):
            return {
                "verified": False,
                "reasoning": raw or "Local AI returned no response.",
                "raw_response": raw,
                "evaluatedAt": now,
            }

        verdict = "FAIL"
        reasoning = raw
        for line in raw.splitlines():
            stripped = line.strip()
            upper = stripped.upper()
            if upper.startswith("VERDICT:"):
                verdict = stripped.split(":", 1)[1].strip().upper()
            elif upper.startswith("REASONING:"):
                reasoning = stripped.split(":", 1)[1].strip()

        return {
            "verified": "PASS" in verdict,
            "reasoning": reasoning,
            "raw_response": raw,
            "evaluatedAt": now,
        }


# Singleton instance
_auditor_instance = None


def get_auditor() -> LocalAIAuditor:
    global _auditor_instance
    if _auditor_instance is None:
        _auditor_instance = LocalAIAuditor()
    return _auditor_instance
