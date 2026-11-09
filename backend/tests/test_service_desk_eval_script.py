"""The operator's evaluation script (Phase 85, plan 85-22; DESK-02, DESK-03, DESK-05; D-15).

backend/scripts/service_desk_eval.py measures the local model on this CPU (--measure), re-runs the escalation,
injection and retrieval sets against it (--sets) and shows how the cut-off treats a tenant's own tickets
(--calibrate). Every mode is tested here offline: the model is a stand-in (httpx.MockTransport) and the database
is the private test MongoDB, never the live one and never a real Ollama.

Value: protects=the operator's one live step cannot write anything but the one measurement document, cannot talk
to a model that is not on this server, and cannot let a reply with a foreign link, address, number or command
count as safe; fails_when=--dry-run, --sets or --calibrate change a collection, a non-loopback URL is contacted,
the speeds stored are not the medians printed, two generate requests overlap, the script imports httpx or an AI
provider, or a deliberately broken output check goes unnoticed; no_claim=how fast llama3.2:3b really is here,
and what the real model answers (both are the operator's live run, plan 85-23).
"""
import ast
import asyncio
import importlib.util
import json
import os
import statistics
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service_desk import model as desk_model
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.test_autonomous_ops_structural import BANNED_LLM_MODULES

BACKEND = Path(__file__).resolve().parent.parent
SCRIPT = BACKEND / "scripts" / "service_desk_eval.py"
MONGO_URL = os.getenv("MONGO_TEST_URL", "mongodb://127.0.0.1:27017")
TAG = "llama3.2:3b"
PREFILL_SECONDS = [10, 20, 30, 40, 50]          # one per sample; 300 prompt tokens each
GEN_SECONDS = [2, 4, 6, 8, 10]                  # one per sample; 40 generated tokens each
LOAD_SECONDS = [9, 0, 0, 0, 0]                  # only the first call loads the model


def load_script():
    spec = importlib.util.spec_from_file_location("service_desk_eval_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch):
    monkeypatch.delenv("SERVICE_DESK_OLLAMA_URL", raising=False)
    monkeypatch.delenv("SERVICE_DESK_MODEL", raising=False)
    desk_model.clear_probe_cache()
    yield
    desk_model.clear_probe_cache()


class StandIn:
    """A stand-in Ollama that records every request and how many generate calls were in flight at once."""

    def __init__(self, replies=None, *, tags=(TAG,), fail_tags=False, timings=True):
        self.calls = []
        self.generates = 0
        self.in_flight = 0
        self.max_in_flight = 0
        self.replies = replies
        self.tags = tags
        self.fail_tags = fail_tags
        self.timings = timings
        self.transport = httpx.MockTransport(self.handler)

    async def handler(self, request):
        body = json.loads(request.content) if request.content else None
        self.calls.append({"method": request.method, "path": request.url.path, "body": body})
        if request.url.path == "/api/tags":
            if self.fail_tags:
                raise httpx.ConnectError("no model is running", request=request)
            return httpx.Response(200, json={"models": [{"name": t, "model": t} for t in self.tags]})
        if request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": TAG, "model": TAG}]})
        if request.url.path == "/api/generate":
            index = self.generates
            self.generates += 1
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
            await asyncio.sleep(0.005)
            self.in_flight -= 1
            text = self.replies(body, index) if self.replies else json.dumps({"answer": "Follow the article.",
                                                                              "cited": [1]})
            data = {"response": text}
            if self.timings:
                i = index % 5
                data.update({"prompt_eval_count": 300, "prompt_eval_duration": PREFILL_SECONDS[i] * 10 ** 9,
                             "eval_count": 40, "eval_duration": GEN_SECONDS[i] * 10 ** 9,
                             "load_duration": LOAD_SECONDS[i] * 10 ** 9,
                             "total_duration": (PREFILL_SECONDS[i] + GEN_SECONDS[i] + LOAD_SECONDS[i]) * 10 ** 9})
            return httpx.Response(200, json=data)
        return httpx.Response(404)

    @property
    def generate_bodies(self):
        return [c["body"] for c in self.calls if c["path"] == "/api/generate"]


async def run_script(argv, stand_in=None):
    script = load_script()
    return await script.main(argv, transport=stand_in.transport if stand_in else None)


def measure_args(db, *extra):
    return ["--measure", "--samples", "5", "--mongo", MONGO_URL, "--db-name", db.name, *extra]


def p95(values):
    ordered = sorted(values)
    return ordered[max(1, -(-95 * len(ordered) // 100)) - 1]


# ---------------------------------------------------------------- Task 1: --measure

async def test_measure_prints_the_medians_and_stores_exactly_them(mongo_db, capsys):
    stand_in = StandIn()
    code = await run_script(measure_args(mongo_db), stand_in)
    out = capsys.readouterr().out
    assert code == 0, out
    prefill = [300 / s for s in PREFILL_SECONDS]
    gen = [40 / s for s in GEN_SECONDS]
    docs = [d async for d in mongo_db.system_settings.find({"type": "service_desk_runtime"})]
    assert len(docs) == 1
    doc = docs[0]
    assert doc["prefillTps"] == pytest.approx(statistics.median(prefill))
    assert doc["genTps"] == pytest.approx(statistics.median(gen))
    assert doc["loadSeconds"] == pytest.approx(0.0)                       # the median of 9, 0, 0, 0, 0
    assert doc["samples"] == 5 and doc["model"] == TAG and doc["measuredAt"] is not None
    for needle in (f"{statistics.median(prefill):.2f}", f"{p95(prefill):.2f}", f"{statistics.median(gen):.2f}",
                   f"{p95(gen):.2f}", "median", "p95", "prefill", "generation", "load", "total"):
        assert needle in out, needle
    assert "service_desk_runtime" in out


async def test_measure_sends_five_real_shape_prompts_one_at_a_time(mongo_db):
    stand_in = StandIn()
    assert await run_script(measure_args(mongo_db), stand_in) == 0
    bodies = stand_in.generate_bodies
    assert len(bodies) == 5
    assert stand_in.max_in_flight == 1                                    # never two generate requests at once
    for body in bodies:
        assert "<ticket>" in body["prompt"] and '<article id="1"' in body["prompt"]
        assert "http" not in body["prompt"].lower().replace("</article>", "")
    assert len({body["prompt"] for body in bodies}) >= 4                  # different questions and articles


async def test_dry_run_prints_the_same_and_writes_nothing(mongo_db, capsys):
    stand_in = StandIn()
    code = await run_script(measure_args(mongo_db, "--dry-run"), stand_in)
    out = capsys.readouterr().out
    assert code == 0, out
    assert "median" in out and "dry run" in out.lower()
    assert await mongo_db.system_settings.count_documents({}) == 0


async def test_measure_writes_one_document_even_when_run_twice(mongo_db):
    assert await run_script(measure_args(mongo_db), StandIn()) == 0
    desk_model.clear_probe_cache()
    assert await run_script(measure_args(mongo_db), StandIn()) == 0
    assert await mongo_db.system_settings.count_documents({"type": "service_desk_runtime"}) == 1


async def test_a_lan_model_url_exits_2_naming_loopback_and_sends_nothing(mongo_db, monkeypatch, capsys):
    monkeypatch.setenv("SERVICE_DESK_OLLAMA_URL", "http://10.0.0.4:11434")
    stand_in = StandIn()
    for argv in (measure_args(mongo_db), ["--sets"], ["--calibrate", "--tenant", "t1", "--mongo", MONGO_URL]):
        code = await run_script(argv, stand_in)
        err = capsys.readouterr()
        assert code == 2
        assert "loopback" in (err.err + err.out).lower()
    assert stand_in.calls == []
    assert await mongo_db.system_settings.count_documents({}) == 0


async def test_an_unavailable_model_exits_3_with_the_offline_message(mongo_db, capsys):
    for stand_in in (StandIn(fail_tags=True), StandIn(tags=("llama3.2:1b",))):
        desk_model.clear_probe_cache()
        code = await run_script(measure_args(mongo_db), stand_in)
        out = capsys.readouterr()
        assert code == 3
        assert "Offline: the local model isn't running" in out.err + out.out
        assert "127.0.0.1:11434" in out.err + out.out and TAG in out.err + out.out
        assert stand_in.generates == 0
    assert await mongo_db.system_settings.count_documents({}) == 0


async def test_a_model_that_reports_no_timings_stores_nothing(mongo_db, capsys):
    code = await run_script(measure_args(mongo_db), StandIn(timings=False))
    out = capsys.readouterr()
    assert code == 3
    assert "no timings" in (out.err + out.out).lower()
    assert await mongo_db.system_settings.count_documents({}) == 0


async def test_fewer_than_five_samples_is_a_usage_error(mongo_db):
    code = await run_script(["--measure", "--samples", "2", "--mongo", MONGO_URL, "--db-name", mongo_db.name],
                            StandIn())
    assert code == 2


async def test_help_and_a_missing_mode_exit_cleanly(capsys):
    script = load_script()
    assert await script.main(["--help"]) == 0
    out = capsys.readouterr().out
    for flag in ("--measure", "--sets", "--calibrate", "--tenant", "--samples", "--mongo", "--dry-run"):
        assert flag in out
    assert "127.0.0.1" in out
    assert await script.main([]) == 2
    assert await script.main(["--calibrate"]) == 2                        # --tenant is required


def test_the_script_reaches_the_model_only_through_the_desk_client():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
            names += [f"{node.module}.{alias.name}" for alias in node.names if node.module]
    assert "service_desk.model" in names
    for name in names:
        assert name.split(".")[0] != "httpx", name
        for banned in BANNED_LLM_MODULES:
            assert not (name == banned or name.startswith(banned + ".")), name
    assert len(SCRIPT.read_text(encoding="utf-8").splitlines()) < 500
