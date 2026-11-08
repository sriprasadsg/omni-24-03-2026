"""The only module that reaches the local model (D-15, DESK-04; PROH-85-02).

A loopback-only Ollama client: the base URL must name 127.0.0.1, ::1 or localhost, and a client built
for any other host refuses every call without sending a byte, so ticket text never leaves this server.
The model must be present under its exact tag (no "first model that is installed" fallback). One
generate call, no streaming, no tools. This is the only desk module that imports httpx, and no desk
module imports an AI provider or any other model client. 85-07 adds caching, the memory check and
timeouts sized from the measurement.
"""
import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx

from . import (DEFAULT_CALL_TIMEOUT, DEFAULT_MODEL, DEFAULT_OLLAMA_URL, KEEP_ALIVE, LOOPBACK_HOSTS, MODEL_ENV,
               NUM_CTX, NUM_PREDICT, OLLAMA_URL_ENV, PROBE_TIMEOUT_SECONDS)

logger = logging.getLogger(__name__)

_NS_PER_MS = 1_000_000
_REPLY_SCHEMA = {"type": "object", "required": ["answer", "cited"],
                 "properties": {"answer": {"type": "string"},
                                "cited": {"type": "array", "items": {"type": "integer"}}}}


class ModelError(Exception):
    """The model could not be reached or did not answer usably."""


@dataclass
class ModelReply:
    text: str
    prompt_tokens: int = 0
    eval_tokens: int = 0
    gen_ms: int = 0
    load_ms: int = 0
    total_ms: int = 0


def _count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def _ms(value: Any) -> int:
    return _count(value) // _NS_PER_MS


class OllamaClient:
    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None, transport: Any = None):
        self.base_url = (base_url or os.getenv(OLLAMA_URL_ENV) or DEFAULT_OLLAMA_URL).rstrip("/")
        self.model = model or os.getenv(MODEL_ENV) or DEFAULT_MODEL
        self._transport = transport
        parsed = urlparse(self.base_url)
        host = (parsed.hostname or "").lower()
        self.refused = parsed.scheme not in ("http", "https") or host not in LOOPBACK_HOSTS
        if self.refused:
            logger.error("service_desk: the model URL is not a loopback address, no call will be sent")

    def _http(self, timeout: httpx.Timeout) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self._transport, timeout=timeout, follow_redirects=False)

    async def available(self) -> bool:
        """True only when the model answers and lists the exact configured tag."""
        if self.refused:
            return False
        try:
            timeout = httpx.Timeout(PROBE_TIMEOUT_SECONDS)
            async with self._http(timeout) as client:
                response = await asyncio.wait_for(client.get(f"{self.base_url}/api/tags"),
                                                  PROBE_TIMEOUT_SECONDS + 1)
            if response.status_code != 200:
                return False
            models = response.json().get("models")
            if not isinstance(models, list):
                return False
            return any(isinstance(m, dict) and self.model in (m.get("name"), m.get("model")) for m in models)
        except Exception:
            return False

    async def generate(self, system: str, prompt: str, *, num_predict: int = NUM_PREDICT,
                       timeout: float = DEFAULT_CALL_TIMEOUT) -> ModelReply:
        """One non-streaming generation. Raises ModelError on refusal, timeout, a non-200 or a bad body."""
        if self.refused:
            raise ModelError("refused: not a loopback address")
        body: Dict[str, Any] = {
            "model": self.model, "system": system, "prompt": prompt, "stream": False, "keep_alive": KEEP_ALIVE,
            "format": _REPLY_SCHEMA,
            "options": {"temperature": 0, "seed": 7, "num_predict": num_predict, "num_ctx": NUM_CTX}}
        limits = httpx.Timeout(connect=3, read=timeout, write=10, pool=3)
        try:
            async with self._http(limits) as client:
                response = await asyncio.wait_for(client.post(f"{self.base_url}/api/generate", json=body),
                                                  timeout + 5)
        except (httpx.HTTPError, asyncio.TimeoutError) as exc:
            raise ModelError(f"no answer: {type(exc).__name__}") from exc
        if response.status_code != 200:
            raise ModelError(f"status {response.status_code}")
        try:
            data = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise ModelError("the answer was not JSON") from exc
        text = data.get("response") if isinstance(data, dict) else None
        if not isinstance(text, str):
            raise ModelError("the answer had no text")
        return ModelReply(text=text, prompt_tokens=_count(data.get("prompt_eval_count")),
                          eval_tokens=_count(data.get("eval_count")), gen_ms=_ms(data.get("eval_duration")),
                          load_ms=_ms(data.get("load_duration")), total_ms=_ms(data.get("total_duration")))
