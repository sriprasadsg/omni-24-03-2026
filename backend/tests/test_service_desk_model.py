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

from datetime import datetime, timedelta, timezone

from service_desk import model as model_module
from service_desk import runtime
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


# ------------------------------------------------------------------ DESK-05: timeouts from the measurement

MEASURED = {"type": "service_desk_runtime", "model": "llama3.2:3b", "prefillTps": 40, "genTps": 8,
            "loadSeconds": 10, "measuredAt": datetime(2026, 11, 8, 9, 0, tzinfo=timezone.utc), "samples": 5}


async def test_with_no_runtime_document_the_defaults_apply_and_are_not_measured(mongo_db):
    m = await runtime.load_measurement(mongo_db)
    assert (m.prefill_tps, m.gen_tps, m.load_seconds, m.measured) == (10, 3, 20, False)
    assert runtime.call_timeout(4000, 220, m) == 280.0


async def test_a_stored_measurement_sizes_the_timeout(mongo_db):
    await mongo_db.system_settings.insert_one(dict(MEASURED))
    m = await runtime.load_measurement(mongo_db)
    assert m.measured is True and (m.prefill_tps, m.gen_tps, m.load_seconds, m.samples) == (40, 8, 10, 5)
    assert m.model == "llama3.2:3b"
    assert runtime.call_timeout(4000, 220, m) == 88.75


@pytest.mark.parametrize("bad", [
    {"prefillTps": 0}, {"genTps": -1}, {"prefillTps": "fast"}, {"genTps": None}, {"loadSeconds": -5},
    {"prefillTps": True}, {"genTps": float("nan")}])
async def test_a_malformed_runtime_document_falls_back_to_the_defaults(mongo_db, bad):
    await mongo_db.system_settings.insert_one({**MEASURED, **bad})
    m = await runtime.load_measurement(mongo_db)
    assert m.measured is False and (m.prefill_tps, m.gen_tps, m.load_seconds) == (10, 3, 20)


async def test_an_unreadable_database_falls_back_to_the_defaults():
    class Broken:
        class system_settings:
            @staticmethod
            async def find_one(*_a, **_k):
                raise RuntimeError("database down")

    m = await runtime.load_measurement(Broken())
    assert m.measured is False and runtime.call_timeout(4000, 220, m) == 280.0


def test_enough_recent_rows_replace_the_generation_estimate_with_their_p95():
    m = runtime.Measurement()
    recent = [20000, 25000, 30000, 35000, 40000, 60000]          # nearest-rank p95 of six values is the largest
    # 1.5 x (4000 / 4 / 10) prefill + 1.5 x 60 s generation + 20 s load
    assert runtime.call_timeout(4000, 220, m, recent) == 150 + 90 + 20
    assert runtime.estimate_seconds(4000, 220, m, recent) == 100 + 60 + 20


def test_fewer_than_five_recent_rows_are_ignored():
    m = runtime.Measurement()
    assert runtime.call_timeout(4000, 220, m, [60000, 60000, 60000, 60000]) == 280.0


def test_the_timeout_is_clamped_to_45_and_300_seconds():
    fast = runtime.Measurement(prefill_tps=1000, gen_tps=1000, load_seconds=0, measured=True)
    assert runtime.call_timeout(40, 10, fast) == 45.0
    assert runtime.call_timeout(40000, 220, runtime.Measurement()) == 300.0
    assert runtime.call_timeout(4000, 220, fast, [500000] * 5) == 300.0


def test_the_estimate_is_the_unscaled_sum():
    m = runtime.Measurement()
    assert runtime.estimate_seconds(4000, 220, m) == round(1000 / 10 + 220 / 3 + 20, 2)
    measured = runtime.Measurement(prefill_tps=40, gen_tps=8, load_seconds=10, measured=True)
    assert runtime.estimate_seconds(4000, 220, measured) == 25 + 27.5 + 10


async def _seed_action(db, action_id, *, gen_ms, minutes_ago, kind="servicedesk", tenant="t1"):
    inputs = {} if gen_ms is None else {"genMs": gen_ms}
    await db.autonomy_actions.insert_one({
        "id": action_id, "tenantId": tenant, "kind": kind, "reason": {"inputs": inputs},
        "createdAt": datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)})


async def test_recent_gen_ms_reads_only_desk_rows_with_a_number_newest_first(mongo_db):
    await _seed_action(mongo_db, "a1", gen_ms=30000, minutes_ago=30)
    await _seed_action(mongo_db, "a2", gen_ms=20000, minutes_ago=10)
    await _seed_action(mongo_db, "a3", gen_ms=None, minutes_ago=5)
    await _seed_action(mongo_db, "a4", gen_ms=99000, minutes_ago=1, kind="isolate_host")
    await _seed_action(mongo_db, "a5", gen_ms="slow", minutes_ago=2)
    await _seed_action(mongo_db, "a6", gen_ms=0, minutes_ago=3)
    await _seed_action(mongo_db, "a7", gen_ms=25000, minutes_ago=20, tenant="t2")
    assert await runtime.recent_gen_ms(mongo_db) == [20000, 25000, 30000]
    assert await runtime.recent_gen_ms(mongo_db, limit=2) == [20000, 25000]


async def test_save_measurement_keeps_exactly_one_document(mongo_db):
    await runtime.save_measurement(mongo_db, dict(MEASURED))
    await runtime.save_measurement(mongo_db, {**MEASURED, "genTps": 9, "samples": 7})
    rows = await mongo_db.system_settings.find({"type": "service_desk_runtime"}).to_list(10)
    assert len(rows) == 1
    assert (rows[0]["genTps"], rows[0]["samples"], rows[0]["prefillTps"]) == (9, 7, 40)
    assert (await runtime.load_measurement(mongo_db)).gen_tps == 9


@pytest.mark.parametrize("bad", [{"prefillTps": 0}, {"genTps": -2}, {"genTps": "8"}, {"loadSeconds": -1},
                                 {"prefillTps": None}])
async def test_save_measurement_rejects_non_positive_rates(mongo_db, bad):
    with pytest.raises(ValueError):
        await runtime.save_measurement(mongo_db, {**MEASURED, **bad})
    assert await mongo_db.system_settings.count_documents({"type": "service_desk_runtime"}) == 0
