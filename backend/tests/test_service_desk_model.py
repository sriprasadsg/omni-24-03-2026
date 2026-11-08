"""The service desk model client and its timeouts (Phase 85, plan 85-07, DESK-03 / DESK-04 / DESK-05). The
client tests use httpx.MockTransport only (no real Ollama, no network); the timeout tests that store a
measurement use the throwaway database of tests/_mongo_test_db.py.

Value: protects=a missing, wrong, remote, busy or memory-starved model is detected before any ticket text is
sent and the desk never substitutes another model; every model call has a timeout sized from what this server
measured, with conservative defaults until a measurement exists; fails_when=a request leaves for a LAN host,
a different tag is accepted, a burst of jobs sends one probe each, a busy or slow model is not reported as
such, or call_timeout drifts from the written formula; no_claim=the hand-off wording and the worker's
feasibility check (85-13, 85-17), the operator measurement script (85-22) and a real Ollama.
"""
import asyncio
import json
import os
import sys
from typing import Any, Dict, List, Optional

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service_desk import model as model_module
from service_desk.model import ModelBusy, ModelError, ModelTimeout, OllamaClient
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)

TAG = "llama3.2:3b"
GB = 1_000_000_000


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("SERVICE_DESK_OLLAMA_URL", raising=False)
    monkeypatch.delenv("SERVICE_DESK_MODEL", raising=False)
    model_module.clear_probe_cache()
    yield
    model_module.clear_probe_cache()


def stand_in(tags: Any = (TAG,), *, tags_status: int = 200, tags_error: bool = False, tags_text: Optional[str] = None,
             loaded: bool = True, generate_status: int = 200, generate_delay: float = 0.0,
             generate_raises: Optional[Exception] = None, size: int = 2 * GB):
    """A stand-in Ollama; returns the transport and the list of requests it received."""
    calls: List[Dict[str, Any]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        calls.append({"method": request.method, "path": request.url.path, "body": body, "host": request.url.host})
        if request.url.path == "/api/tags":
            if tags_error:
                raise httpx.ConnectError("refused", request=request)
            if tags_text is not None:
                return httpx.Response(tags_status, text=tags_text)
            return httpx.Response(tags_status, json={"models": [{"name": t, "model": t, "size": size} for t in tags]})
        if request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": TAG, "model": TAG}] if loaded else []})
        if request.url.path == "/api/generate":
            if generate_delay:
                await asyncio.sleep(generate_delay)
            if generate_raises:
                raise generate_raises
            return httpx.Response(generate_status, json={"response": '{"answer": "ok", "cited": [1]}',
                                                         "eval_count": 5, "eval_duration": 1_000_000_000})
        return httpx.Response(404)

    return httpx.MockTransport(handler), calls


def paths(calls: List[Dict[str, Any]]) -> List[str]:
    return [c["path"] for c in calls]


def client(transport, *, base_url: str = "http://127.0.0.1:11434", **kwargs) -> OllamaClient:
    return OllamaClient(base_url, TAG, transport=transport, **kwargs)


# ------------------------------------------------------------------ DESK-04: the exact tag on loopback

async def test_available_is_false_when_the_model_cannot_be_reached():
    transport, calls = stand_in(tags_error=True)
    assert await client(transport).available() is False
    assert paths(calls) == ["/api/tags"]


async def test_available_is_false_when_the_tag_list_answers_5xx():
    transport, _ = stand_in(tags_status=500, tags_text="boom")
    assert await client(transport).available() is False


async def test_available_is_false_when_only_a_smaller_tag_is_installed():
    transport, calls = stand_in(tags=["llama3.2:1b"])
    c = client(transport)
    assert await c.available() is False
    assert "/api/generate" not in paths(calls)


async def test_available_is_false_when_only_the_instruct_tag_is_installed():
    transport, calls = stand_in(tags=["llama3.2:3b-instruct"])
    assert await client(transport).available() is False
    assert "/api/generate" not in paths(calls)


async def test_available_is_false_when_the_tag_list_is_not_json():
    transport, _ = stand_in(tags_text="<html>not json</html>")
    assert await client(transport).available() is False


async def test_available_is_false_when_the_tag_list_has_the_wrong_shape():
    transport, _ = stand_in(tags_text=json.dumps({"models": "llama3.2:3b"}))
    assert await client(transport).available() is False


async def test_available_is_true_only_for_the_exact_tag():
    transport, calls = stand_in(tags=["llama3.2:1b", TAG])
    assert await client(transport).available() is True
    assert paths(calls) == ["/api/tags"]


async def test_a_lan_address_is_refused_without_any_request():
    transport, calls = stand_in()
    c = client(transport, base_url="http://192.168.1.5:11434")
    assert await c.available() is False
    with pytest.raises(ModelError):
        await c.generate("system", "prompt")
    assert calls == []


@pytest.mark.parametrize("url", ["http://localhost:11434", "http://[::1]:11434", "http://127.0.0.1:11434"])
async def test_loopback_hosts_are_accepted(url):
    transport, calls = stand_in()
    assert await client(transport, base_url=url).available() is True
    assert len(calls) == 1


@pytest.mark.parametrize("url", ["http://localhost.evil.example:11434", "http://127.0.0.1.example:11434",
                                 "ftp://127.0.0.1:11434", "http://10.0.0.4:11434"])
async def test_look_alike_and_non_http_urls_are_refused(url):
    transport, calls = stand_in()
    assert await client(transport, base_url=url).available() is False
    assert calls == []


# ------------------------------------------------------------------ the availability cache

async def test_two_checks_within_the_cache_window_send_one_tags_request():
    transport, calls = stand_in()
    now = [1000.0]
    c = client(transport, clock=lambda: now[0])
    assert await c.available() is True
    now[0] += 14
    assert await c.available() is True
    assert paths(calls) == ["/api/tags"]


async def test_a_check_after_the_cache_window_probes_again():
    transport, calls = stand_in()
    now = [1000.0]
    c = client(transport, clock=lambda: now[0])
    await c.available()
    now[0] += 16
    await c.available()
    assert paths(calls) == ["/api/tags", "/api/tags"]


async def test_the_cache_is_shared_by_clients_of_the_same_url_and_tag():
    transport, calls = stand_in()
    now = [50.0]
    await client(transport, clock=lambda: now[0]).available()
    await client(transport, clock=lambda: now[0]).available()
    assert paths(calls) == ["/api/tags"]


async def test_a_failed_probe_is_cached_too():
    transport, calls = stand_in(tags_error=True)
    now = [1.0]
    c = client(transport, clock=lambda: now[0])
    assert await c.available() is False
    assert await c.available() is False
    assert len(calls) == 1


# ------------------------------------------------------------------ generate: busy, timeout, error

async def test_generate_sends_the_cpu_threads_and_keep_alive():
    transport, calls = stand_in()
    reply = await client(transport).generate("system", "prompt")
    sent = [c for c in calls if c["path"] == "/api/generate"]
    assert len(sent) == 1
    assert sent[0]["body"]["keep_alive"] == "30m"
    assert sent[0]["body"]["options"]["num_thread"] == max(1, (os.cpu_count() or 2) - 1)
    assert sent[0]["host"] == "127.0.0.1"
    assert reply.text and reply.eval_tokens == 5


async def test_generate_maps_503_to_busy():
    transport, _ = stand_in(generate_status=503)
    with pytest.raises(ModelBusy):
        await client(transport).generate("system", "prompt")


async def test_generate_maps_400_to_a_plain_model_error():
    transport, _ = stand_in(generate_status=400)
    with pytest.raises(ModelError) as caught:
        await client(transport).generate("system", "prompt")
    assert not isinstance(caught.value, (ModelBusy, ModelTimeout))


async def test_generate_maps_a_read_timeout_to_timeout():
    transport, _ = stand_in(generate_raises=httpx.ReadTimeout("slow"))
    with pytest.raises(ModelTimeout):
        await client(transport).generate("system", "prompt", timeout=0.2)


async def test_generate_maps_a_wait_that_runs_out_to_timeout(monkeypatch):
    monkeypatch.setattr(model_module, "_WAIT_GRACE_SECONDS", 0.05)
    transport, _ = stand_in(generate_delay=1.0)
    with pytest.raises(ModelTimeout):
        await client(transport).generate("system", "prompt", timeout=0.2)


async def test_generate_fails_when_the_tag_vanished_and_never_tries_another():
    transport, calls = stand_in(tags=["llama3.2:1b"])
    with pytest.raises(ModelError):
        await client(transport).generate("system", "prompt")
    assert "/api/generate" not in paths(calls)


# ------------------------------------------------------------------ the memory check before a cold load

async def test_a_cold_model_with_too_little_free_memory_is_busy_before_any_generate_request():
    transport, calls = stand_in(loaded=False, size=2 * GB)
    c = client(transport, meminfo_reader=lambda: 3 * GB)        # 2 GB + 1.5 GB needed, 3 GB free
    with pytest.raises(ModelBusy):
        await c.generate("system", "prompt")
    assert "/api/generate" not in paths(calls)
    assert "/api/ps" in paths(calls)


async def test_a_cold_model_with_enough_free_memory_is_generated():
    transport, calls = stand_in(loaded=False, size=2 * GB)
    c = client(transport, meminfo_reader=lambda: 4 * GB)
    assert (await c.generate("system", "prompt")).text
    assert "/api/generate" in paths(calls)


async def test_a_loaded_model_skips_the_memory_check():
    transport, calls = stand_in(loaded=True, size=2 * GB)

    def starved() -> int:
        raise AssertionError("the memory is not read for a model already in memory")

    assert (await client(transport, meminfo_reader=starved).generate("system", "prompt")).text
    assert "/api/generate" in paths(calls)


def test_memory_ok_compares_available_memory_with_size_plus_headroom():
    assert model_module.memory_ok(2 * GB, lambda: 3_500_000_000) is True
    assert model_module.memory_ok(2 * GB, lambda: 3_499_999_999) is False


def test_an_unreadable_meminfo_counts_as_enough():
    assert model_module.memory_ok(2 * GB, lambda: None) is True

    def broken() -> int:
        raise OSError("no /proc")

    assert model_module.memory_ok(2 * GB, broken) is True


def test_the_real_meminfo_reader_answers_bytes_or_none():
    value = model_module._read_meminfo()
    assert value is None or value > 0
