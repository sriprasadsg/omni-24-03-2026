#!/usr/bin/env python3
"""The operator's script for the first-line service desk's local model (Phase 85, plan 85-22).

It does the three things this VM could not do while Ollama was not installed:

  --measure    DESK-05  how fast llama3.2:3b really is on this CPU, stored for the desk's timeouts
  --sets       DESK-02, DESK-03  the escalation, injection and retrieval sets against the real model
  --calibrate  DESK-02  how the retrieval cut-off treats one tenant's own Help desk articles and tickets

Run it from the repository root with the backend's Python, at a quiet time, in this order:

  1. Install Ollama and bind it to this server only (OLLAMA_HOST=127.0.0.1:11434, and the optional drop-in
     OLLAMA_NUM_PARALLEL=1 and OLLAMA_MAX_LOADED_MODELS=1), then pull the model:
         ollama pull llama3.2:3b
         curl http://127.0.0.1:11434/api/tags          # must list llama3.2:3b
  2. Rehearse the measurement; it sends 5 prompts and writes nothing:
         backend/venv/bin/python backend/scripts/service_desk_eval.py --measure --dry-run
  3. Measure for real. This stores one service_desk_runtime document, which the timeouts read from then on.
     Watch the API latency while it runs (the model keeps one core free, but check):
         backend/venv/bin/python backend/scripts/service_desk_eval.py --measure --mongo "$MONGODB_URL"
  4. Run the sets against the real model (read only, about 34 model calls, so it takes a while on a CPU):
         backend/venv/bin/python backend/scripts/service_desk_eval.py --sets
     It exits 1 when any reply passes the output checks while carrying a link, address, phone number or
     command its cited article lacks, or when an escalation case would reach the model.
  5. Calibrate on a real tenant (read only; no model call is made):
         backend/venv/bin/python backend/scripts/service_desk_eval.py --calibrate --tenant <tenant id> \\
             --mongo "$MONGODB_URL"
     It prints each recent person-raised ticket's best score, the words it shares with the article and whether
     the pinned cut-off accepts it. It never changes the cut-off: that stays a reviewed change to retrieval.py.

The database is the one named by --mongo (default: MONGODB_URL, MONGO_URI or MONGODB_URI) and --db-name
(default: MONGODB_DB_NAME, else omni_platform). Only --measure without --dry-run writes anything: the one
document. The model is reached only through service_desk.model.OllamaClient, which sends nothing unless
SERVICE_DESK_OLLAMA_URL (default http://127.0.0.1:11434) names this server; this script refuses to start
otherwise. It imports no cloud provider. Exit codes: 0 done, 1 a check failed, 2 wrong usage or a refused
URL, 3 the model or the database is not available.
"""
import argparse
import asyncio
import json
import math
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from service_desk import CALL_TIMEOUT_MAX, DEFAULT_OLLAMA_URL, OLLAMA_URL_ENV, retrieval, runtime, starters  # noqa: E402
from service_desk.model import ModelError, OllamaClient, clear_probe_cache  # noqa: E402
from service_desk.sanitize import build_prompt  # noqa: E402

FIXTURES = _BACKEND / "tests" / "fixtures" / "service_desk"
MIN_SAMPLES = 5
MAX_SAMPLES = 40
DEFAULT_DB_NAME = "omni_platform"
EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_UNAVAILABLE = 0, 1, 2, 3


# ---------------------------------------------------------------- small helpers

def load_jsonl(name: str) -> List[Dict[str, Any]]:
    """The cases of one fixture file (the comment row is dropped)."""
    path = FIXTURES / name
    if not path.is_file():
        raise FileNotFoundError(f"the fixture {path} is missing; run this script from a full checkout")
    with path.open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    return [row for row in rows if "_comment" not in row]


def median(values: Sequence[float]) -> float:
    return float(statistics.median(values))


def p95(values: Sequence[float]) -> float:
    """The 95th percentile by nearest rank, the same rule runtime.py uses."""
    ordered = sorted(values)
    return float(ordered[max(1, math.ceil(0.95 * len(ordered))) - 1])


def say(text: str = "") -> None:
    print(text, flush=True)


def complain(text: str) -> None:
    print(text, file=sys.stderr, flush=True)


def starter_docs() -> List[Dict[str, Any]]:
    """The four starter articles as the retrieval stage reads a tenant's articles."""
    return [{"id": s["key"], "title": s["title"], "content": s["content"], "tags": list(s["tags"])}
            for s in starters.STARTERS]


def offline_message(client: OllamaClient) -> str:
    where = client.base_url.split("://", 1)[-1]
    return (f"Offline: the local model isn't running. Ollama is not reachable at {where}, or the tag "
            f"{client.model} has not been pulled (ollama pull {client.model}).")


async def open_database(args: argparse.Namespace):
    """(client, db) for the database named by the arguments, or (None, None) after printing why not."""
    url = args.mongo or os.getenv("MONGODB_URL") or os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
    if not url:
        complain("No database: pass --mongo or set MONGODB_URL.")
        return None, None
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(url, serverSelectionTimeoutMS=3000)
    try:
        await client.admin.command("ping")
    except Exception as exc:
        client.close()
        complain(f"The database is not reachable ({type(exc).__name__}).")
        return None, None
    return client, client[args.db_name]


# ---------------------------------------------------------------- --measure (DESK-05)

def measure_prompts(count: int) -> List[Tuple[str, str, str]]:
    """(question, system, prompt) for ``count`` real-shape prompts: the retrieval set's questions that must
    match, taken in turn from each starter article, each with the articles the desk would really send."""
    docs = starter_docs()
    by_article: Dict[str, List[Dict[str, Any]]] = {}
    for case in load_jsonl("retrieval_set.jsonl"):
        if case.get("expect") == "match":
            by_article.setdefault(case["article"], []).append(case)
    prompts: List[Tuple[str, str, str]] = []
    while len(prompts) < count and any(by_article.values()):
        for key in list(by_article):
            if not by_article[key] or len(prompts) >= count:
                continue
            question = by_article[key].pop(0)["question"]
            matches = retrieval.select(retrieval.score(question, docs))
            if matches:
                system, prompt = build_prompt(question, "", matches)
                prompts.append((question, system, prompt))
    return prompts


def _sample(reply: Any, wall_seconds: float) -> Dict[str, Optional[float]]:
    """One call's numbers: seconds in total and for the load, tokens per second for the prompt and the reply."""
    prefill = reply.prompt_tokens / (reply.prefill_ms / 1000) if reply.prompt_tokens and reply.prefill_ms else None
    gen = reply.eval_tokens / (reply.gen_ms / 1000) if reply.eval_tokens and reply.gen_ms else None
    return {"total": (reply.total_ms / 1000) if reply.total_ms else wall_seconds, "load": reply.load_ms / 1000,
            "prefill": prefill, "gen": gen}


def _line(label: str, values: Sequence[float], unit: str, slowest: bool = False) -> str:
    text = f"  {label:<24} median {median(values):9.2f} {unit}   p95 {p95(values):9.2f} {unit}"
    return text + (f"   slowest {min(values):9.2f} {unit}" if slowest else "")


async def run_measure(client: OllamaClient, args: argparse.Namespace) -> int:
    prompts = measure_prompts(args.samples)
    if len(prompts) < args.samples:
        complain(f"Only {len(prompts)} usable prompts were found in the retrieval set.")
        return EXIT_USAGE
    say(f"Measuring {client.model} with {len(prompts)} prompts, one at a time (timeout {CALL_TIMEOUT_MAX} s each).")
    rows: List[Dict[str, Optional[float]]] = []
    for number, (question, system, prompt) in enumerate(prompts, start=1):
        started = time.monotonic()
        try:
            reply = await client.generate(system, prompt, timeout=float(CALL_TIMEOUT_MAX))
        except ModelError as exc:
            complain(f"Sample {number} failed: {exc}. Nothing was stored.")
            return EXIT_UNAVAILABLE
        rows.append(_sample(reply, time.monotonic() - started))
        say(f"  sample {number}/{len(prompts)}: {rows[-1]['total']:.1f} s ({len(system) + len(prompt)} characters)")
    usable = [row for row in rows if row["prefill"] and row["gen"]]
    if len(usable) < MIN_SAMPLES:
        complain(f"The model reported no timings for {len(rows) - len(usable)} of {len(rows)} samples "
                 f"(no timings means no measurement). Nothing was stored.")
        return EXIT_UNAVAILABLE
    totals, loads = [r["total"] for r in usable], [r["load"] for r in usable]
    prefill, gen = [r["prefill"] for r in usable], [r["gen"] for r in usable]
    say("")
    say(f"Result for {client.model} on this server ({len(usable)} samples):")
    say(_line("total time", totals, "s"))
    say(_line("load time", loads, "s"))
    say(_line("prefill speed", prefill, "tokens/s", slowest=True))
    say(_line("generation speed", gen, "tokens/s", slowest=True))
    say(f"  the first sample loaded the model in {usable[0]['load']:.1f} s; the longest load was {max(loads):.1f} s")
    document = {"model": client.model, "prefillTps": median(prefill), "genTps": median(gen),
                "loadSeconds": median(loads), "samples": len(usable), "measuredAt": datetime.now(timezone.utc)}
    estimate = runtime.Measurement(model=client.model, prefill_tps=document["prefillTps"],
                                   gen_tps=document["genTps"], load_seconds=document["loadSeconds"], measured=True)
    say(f"  a 4,000-character prompt would get a {runtime.call_timeout(4000, 220, estimate):.0f} s timeout")
    if args.dry_run:
        say("Dry run: nothing was written. Without --dry-run this stores the medians above as service_desk_runtime.")
        return EXIT_OK
    mongo, db = await open_database(args)
    if db is None:
        return EXIT_UNAVAILABLE
    try:
        await runtime.save_measurement(db, document)
    except Exception as exc:                  # an unusable number or an unwritable database
        complain(f"The measurement could not be stored: {exc}")
        return EXIT_UNAVAILABLE
    finally:
        mongo.close()
    say(f"Stored: the service_desk_runtime document in {args.db_name}. The desk's timeouts now use it.")
    return EXIT_OK


async def run_sets(client: OllamaClient, args: argparse.Namespace) -> int:
    complain("--sets is not available yet.")
    return EXIT_USAGE


async def run_calibrate(args: argparse.Namespace) -> int:
    complain("--calibrate is not available yet.")
    return EXIT_USAGE


# ---------------------------------------------------------------- entry point

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="service_desk_eval.py", description="The operator's measurement, live-set and calibration script "
        "for the service desk's local model. The model must be on this server (127.0.0.1); see the top of this file.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--measure", action="store_true",
                      help="measure the model's speed on this CPU and store it for the timeouts")
    mode.add_argument("--sets", action="store_true",
                      help="run the escalation, injection and retrieval sets against the real model (read only)")
    mode.add_argument("--calibrate", action="store_true",
                      help="show how the cut-off treats a tenant's articles and recent tickets (read only)")
    parser.add_argument("--tenant", help="the tenant id for --calibrate")
    parser.add_argument("--samples", type=int, default=MIN_SAMPLES,
                        help=f"prompts to send for --measure, {MIN_SAMPLES} to {MAX_SAMPLES} (default {MIN_SAMPLES})")
    parser.add_argument("--mongo", default=None, help="MongoDB URL (default: the MONGODB_URL environment variable)")
    parser.add_argument("--db-name", default=os.getenv("MONGODB_DB_NAME") or DEFAULT_DB_NAME,
                        help=f"database name (default: MONGODB_DB_NAME, else {DEFAULT_DB_NAME})")
    parser.add_argument("--dry-run", action="store_true", help="with --measure: do everything but store the result")
    return parser


async def main(argv: Optional[Sequence[str]] = None, *, transport: Any = None) -> int:
    """Run one mode and return the exit code. ``transport`` lets a test stand in for the model."""
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else EXIT_USAGE
    if args.calibrate and not args.tenant:
        complain("--calibrate needs --tenant <tenant id>.")
        return EXIT_USAGE
    if args.measure and not MIN_SAMPLES <= args.samples <= MAX_SAMPLES:
        complain(f"--samples must be between {MIN_SAMPLES} and {MAX_SAMPLES}.")
        return EXIT_USAGE
    clear_probe_cache()
    client = OllamaClient(transport=transport)
    if client.refused:
        complain(f"Refused: {OLLAMA_URL_ENV} is {client.base_url!r}, which is not a loopback address. The model "
                 f"must run on this server (127.0.0.1, ::1 or localhost; default {DEFAULT_OLLAMA_URL}). "
                 "Nothing was sent.")
        return EXIT_USAGE
    if args.calibrate:
        return await run_calibrate(args)
    if not await client.available():
        complain(offline_message(client))
        return EXIT_UNAVAILABLE
    return await (run_measure(client, args) if args.measure else run_sets(client, args))


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
