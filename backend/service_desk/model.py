"""The only module that reaches the local model (D-15, DESK-04; PROH-85-02).

A loopback-only Ollama client: the base URL must name 127.0.0.1, ::1 or localhost, and a client built
for any other host refuses every call without sending a byte, so ticket text never leaves this server.
The model must be present under its exact tag (no "first model that is installed" fallback, and never a
retry against another tag). One generate call, no streaming, no tools. This is the only desk module that
imports httpx, and no desk module imports an AI provider or any other model client.

The availability answer is cached for PROBE_CACHE_SECONDS per base URL and tag, so a burst of jobs
sends one /api/tags request. Before a cold load the free memory is compared with the model size plus
headroom, and a busy model (503) or a memory shortfall is reported as ModelBusy so the ticket goes to
a person instead of queueing behind a model that cannot answer. Timeouts are sized from the operator's
measurement (runtime.py); every request leaves one core free for the API and MongoDB.
"""
import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.parse import urlparse

import httpx

from . import (DEFAULT_CALL_TIMEOUT, DEFAULT_MODEL, DEFAULT_OLLAMA_URL, KEEP_ALIVE, LOOPBACK_HOSTS, MODEL_ENV,
               NUM_CTX, NUM_PREDICT, OLLAMA_URL_ENV, PROBE_CACHE_SECONDS, PROBE_TIMEOUT_SECONDS)

logger = logging.getLogger(__name__)

_NS_PER_MS = 1_000_000
_REPLY_SCHEMA = {"type": "object", "required": ["answer", "cited"],
                 "properties": {"answer": {"type": "string"},
                                "cited": {"type": "array", "items": {"type": "integer"}}}}


class ModelError(Exception):
    """The model could not be reached or did not answer usably."""


class ModelBusy(ModelError):
    """The model is overloaded (503) or too little memory is free to load it: hand the ticket to a person."""


class ModelTimeout(ModelError):
    """The model did not answer within the call timeout."""


@dataclass
class ModelReply:
    text: str
    prompt_tokens: int = 0
    eval_tokens: int = 0
    gen_ms: int = 0
    load_ms: int = 0
    total_ms: int = 0
    prefill_ms: int = 0


MEMORY_HEADROOM_BYTES = 1_500_000_000       # research A-assumed: model size plus 1.5 GB must be free
_WAIT_GRACE_SECONDS = 1.0                   # asyncio.wait_for outlasts the read timeout by this much

# (base_url, model) -> (checked_at, available, model_size_bytes, transport). The transport is kept so that
# a client built on a different stand-in transport (a test) never reads another client's answer; in
# production it is None for every client, so the entry is shared per base URL and tag.
_PROBE_CACHE: Dict[Tuple[str, str], Tuple[float, bool, int, Any]] = {}


def clear_probe_cache() -> None:
    _PROBE_CACHE.clear()


def _count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def _ms(value: Any) -> int:
    return _count(value) // _NS_PER_MS


def _read_meminfo() -> Optional[int]:
    """MemAvailable in bytes from /proc/meminfo, or None when it cannot be read."""
    try:
        with open("/proc/meminfo", encoding="ascii") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def memory_ok(model_size_bytes: int, meminfo_reader: Callable[[], Optional[int]] = _read_meminfo) -> bool:
    """True when MemAvailable covers the model size plus headroom. An unreadable meminfo counts as enough:
    the call timeout still bounds what a slow, swapping load can cost."""
    try:
        available = meminfo_reader()
    except Exception:
        return True
    if available is None:
        return True
    return available >= max(0, int(model_size_bytes or 0)) + MEMORY_HEADROOM_BYTES


def cpu_threads() -> int:
    """One core stays free for the API and MongoDB."""
    return max(1, (os.cpu_count() or 2) - 1)


class OllamaClient:
    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None, transport: Any = None,
                 clock: Callable[[], float] = time.monotonic,
                 meminfo_reader: Callable[[], Optional[int]] = _read_meminfo):
        self.base_url = (base_url or os.getenv(OLLAMA_URL_ENV) or DEFAULT_OLLAMA_URL).rstrip("/")
        self.model = model or os.getenv(MODEL_ENV) or DEFAULT_MODEL
        self._transport = transport
        self._clock = clock
        self._meminfo_reader = meminfo_reader
        parsed = urlparse(self.base_url)
        try:
            host = (parsed.hostname or "").lower()
        except ValueError:
            host = ""
        self.refused = parsed.scheme not in ("http", "https") or host not in LOOPBACK_HOSTS
        if self.refused:
            logger.error("service_desk: the model URL is not a loopback address, no call will be sent")

    def _http(self, timeout: httpx.Timeout) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self._transport, timeout=timeout, follow_redirects=False)

    async def _get(self, path: str) -> httpx.Response:
        timeout = httpx.Timeout(PROBE_TIMEOUT_SECONDS)
        async with self._http(timeout) as client:
            return await asyncio.wait_for(client.get(f"{self.base_url}{path}"), PROBE_TIMEOUT_SECONDS + 1)

    async def _probe(self) -> Tuple[bool, int]:
        """(available, model size in bytes) from one /api/tags request. Never raises."""
        try:
            response = await self._get("/api/tags")
            if response.status_code != 200:
                return False, 0
            models = response.json().get("models")
            if not isinstance(models, list):
                return False, 0
            for entry in models:
                if isinstance(entry, dict) and self.model in (entry.get("name"), entry.get("model")):
                    return True, _count(entry.get("size"))
            return False, 0
        except Exception:
            return False, 0

    async def _probe_cached(self) -> Tuple[bool, int]:
        key = (self.base_url, self.model)
        now = self._clock()
        cached = _PROBE_CACHE.get(key)
        if cached and cached[3] is self._transport and 0 <= now - cached[0] < PROBE_CACHE_SECONDS:
            return cached[1], cached[2]
        available, size = await self._probe()
        _PROBE_CACHE[key] = (now, available, size, self._transport)
        return available, size

    async def available(self) -> bool:
        """True only when the model answers and lists the exact configured tag (cached 15 s). A URL that is
        not loopback is False without any request."""
        if self.refused:
            return False
        return (await self._probe_cached())[0]

    async def loaded(self) -> bool:
        """True when /api/ps lists the tag, that is, the model is already in memory."""
        if self.refused:
            return False
        try:
            response = await self._get("/api/ps")
            if response.status_code != 200:
                return False
            models = response.json().get("models")
            return isinstance(models, list) and any(
                isinstance(entry, dict) and self.model in (entry.get("name"), entry.get("model"))
                for entry in models)
        except Exception:
            return False

    async def generate(self, system: str, prompt: str, *, num_predict: int = NUM_PREDICT,
                       timeout: float = DEFAULT_CALL_TIMEOUT) -> ModelReply:
        """One non-streaming generation. Raises ModelBusy (503, or too little memory for a cold load),
        ModelTimeout (the call outlasted its timeout) or ModelError (refusal, the tag is gone, any other
        non-200, a bad body). Never retries and never tries another tag."""
        if self.refused:
            raise ModelError("refused: not a loopback address")
        available, size = await self._probe_cached()
        if not available:
            raise ModelError("the model is not listed")
        if not await self.loaded() and not memory_ok(size, self._meminfo_reader):
            raise ModelBusy("not enough free memory to load the model")
        body: Dict[str, Any] = {
            "model": self.model, "system": system, "prompt": prompt, "stream": False, "keep_alive": KEEP_ALIVE,
            "format": _REPLY_SCHEMA,
            "options": {"temperature": 0, "seed": 7, "num_predict": num_predict, "num_ctx": NUM_CTX,
                        "num_thread": cpu_threads()}}
        limits = httpx.Timeout(connect=3, read=timeout, write=10, pool=3)
        try:
            async with self._http(limits) as client:
                response = await asyncio.wait_for(client.post(f"{self.base_url}/api/generate", json=body),
                                                  timeout + _WAIT_GRACE_SECONDS)
        except (httpx.TimeoutException, asyncio.TimeoutError) as exc:
            raise ModelTimeout(f"no answer in time: {type(exc).__name__}") from exc
        except httpx.HTTPError as exc:
            raise ModelError(f"no answer: {type(exc).__name__}") from exc
        if response.status_code == 503:
            raise ModelBusy("the model is busy")
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
                          load_ms=_ms(data.get("load_duration")), total_ms=_ms(data.get("total_duration")),
                          prefill_ms=_ms(data.get("prompt_eval_duration")))
