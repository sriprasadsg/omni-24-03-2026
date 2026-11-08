"""Model call timeouts sized for this CPU from a real measurement (DESK-05).

The server runs the model on CPU only, so a fixed timeout is either too short (every answer is lost) or
too long (a stuck call blocks the one worker). The timeout is built from three speeds:

    call_timeout = clamp(1.5 x (prompt_tokens / prefillTps + num_predict / genTps) + loadSeconds, 45, 300)

with prompt_tokens estimated as characters / 4. The speeds come from the single ``service_desk_runtime``
document in ``system_settings`` that the operator's measurement script fills (85-22). With no document, or
one that cannot be read, conservative defaults apply and ``measured`` is False (the status line then says
"not measured"). Once 5 or more desk rows carry a real ``reason.inputs.genMs``, the generation part is
1.5 x their 95th percentile instead of the rate-based estimate. ``estimate_seconds`` is the same sum without
the 1.5 safety factor: the worker's feasibility check (85-17) uses it as the expected duration.
Nothing here sends a request; the real speeds of this server are a step for the operator, not a test.
"""
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from autonomous_ops.scope import raw

from . import (CALL_TIMEOUT_MAX, CALL_TIMEOUT_MIN, DEFAULT_GEN_TPS, DEFAULT_LOAD_SECONDS, DEFAULT_MODEL,
               DEFAULT_PREFILL_TPS, KIND, store)

logger = logging.getLogger(__name__)

DOC_TYPE = "service_desk_runtime"
SAFETY_FACTOR = 1.5
CHARS_PER_TOKEN = 4
MIN_RECENT_SAMPLES = 5
RECENT_LIMIT = 50


@dataclass
class Measurement:
    model: str = DEFAULT_MODEL
    prefill_tps: float = float(DEFAULT_PREFILL_TPS)
    gen_tps: float = float(DEFAULT_GEN_TPS)
    load_seconds: float = float(DEFAULT_LOAD_SECONDS)
    measured: bool = False
    measured_at: Optional[datetime] = None
    samples: int = 0


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _from_document(doc: Any) -> Optional[Measurement]:
    """A Measurement from a stored document, or None when any speed is missing, non-numeric or not positive."""
    if not isinstance(doc, dict):
        return None
    prefill, gen, load = _number(doc.get("prefillTps")), _number(doc.get("genTps")), _number(doc.get("loadSeconds"))
    if prefill is None or gen is None or load is None or prefill <= 0 or gen <= 0 or load < 0:
        return None
    samples = doc.get("samples")
    measured_at = doc.get("measuredAt")
    model = doc.get("model")
    return Measurement(model=model if isinstance(model, str) and model else DEFAULT_MODEL,
                       prefill_tps=prefill, gen_tps=gen, load_seconds=load, measured=True,
                       measured_at=measured_at if isinstance(measured_at, datetime) else None,
                       samples=samples if isinstance(samples, int) and not isinstance(samples, bool) else 0)


async def load_measurement(db) -> Measurement:
    """The operator's measurement, or the conservative defaults (measured False). Never raises."""
    try:
        doc = await store.runtime_settings(db).find_one({"type": DOC_TYPE}, {"_id": 0})
    except Exception as exc:
        logger.warning("service_desk: the runtime measurement could not be read: %s", exc)
        return Measurement()
    return _from_document(doc) or Measurement()


async def recent_gen_ms(db, limit: int = RECENT_LIMIT) -> List[int]:
    """The generation time in milliseconds of the newest desk rows that carry one (read only)."""
    try:
        cursor = raw(db).autonomy_actions.find(
            {"kind": KIND, "reason.inputs.genMs": {"$type": "number", "$gt": 0}},
            {"_id": 0, "reason.inputs.genMs": 1}).sort("createdAt", -1).limit(max(1, limit))
        rows = await cursor.to_list(length=max(1, limit))
    except Exception as exc:
        logger.warning("service_desk: recent generation times could not be read: %s", exc)
        return []
    values = []
    for row in rows:
        value = _number((((row or {}).get("reason") or {}).get("inputs") or {}).get("genMs"))
        if value is not None and value > 0:
            values.append(int(value))
    return values


def _p95_seconds(gen_ms: Sequence[int]) -> float:
    """The 95th percentile by nearest rank, in seconds."""
    ordered = sorted(gen_ms)
    rank = max(1, math.ceil(0.95 * len(ordered)))
    return ordered[rank - 1] / 1000.0


def _generation_seconds(num_predict: int, m: Measurement, recent: Optional[Sequence[int]], *, safety: float) -> float:
    if recent is not None and len(recent) >= MIN_RECENT_SAMPLES:
        return safety * _p95_seconds(recent)
    return safety * (max(0, num_predict) / m.gen_tps)


def _prefill_seconds(prompt_chars: int, m: Measurement, *, safety: float) -> float:
    return safety * (max(0, prompt_chars) / CHARS_PER_TOKEN / m.prefill_tps)


def call_timeout(prompt_chars: int, num_predict: int, m: Measurement, recent: Optional[Sequence[int]] = None) -> float:
    """The timeout for one model call in seconds (rounded to two places), clamped to 45..300."""
    total = (_prefill_seconds(prompt_chars, m, safety=SAFETY_FACTOR)
             + _generation_seconds(num_predict, m, recent, safety=SAFETY_FACTOR) + m.load_seconds)
    return round(min(float(CALL_TIMEOUT_MAX), max(float(CALL_TIMEOUT_MIN), total)), 2)


def estimate_seconds(prompt_chars: int, num_predict: int, m: Measurement,
                     recent: Optional[Sequence[int]] = None) -> float:
    """The expected duration of one call: the same sum as call_timeout without the 1.5 factor."""
    total = (_prefill_seconds(prompt_chars, m, safety=1.0)
             + _generation_seconds(num_predict, m, recent, safety=1.0) + m.load_seconds)
    return round(total, 2)


async def save_measurement(db, doc: Dict[str, Any]) -> Dict[str, Any]:
    """Upsert the one ``service_desk_runtime`` document (the operator script, 85-22). Rejects a speed that
    is missing or not positive with ValueError and stores nothing."""
    candidate = _from_document(doc)
    if candidate is None:
        raise ValueError("prefillTps and genTps must be positive numbers and loadSeconds must not be negative")
    stored = {"type": DOC_TYPE, "model": candidate.model, "prefillTps": candidate.prefill_tps,
              "genTps": candidate.gen_tps, "loadSeconds": candidate.load_seconds,
              "measuredAt": candidate.measured_at or datetime.now(timezone.utc), "samples": max(1, candidate.samples)}
    await store.runtime_settings(db).update_one({"type": DOC_TYPE}, {"$set": stored}, upsert=True)
    return stored
