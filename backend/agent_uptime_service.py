"""
Agent Uptime Service — Phase 48 (FOBS-02, D-01a)

On-the-fly gap-detection uptime computation over `agent_metrics` heartbeat
rows. Uptime is defined (D-01) as a heartbeat-presence ratio
(received/expected buckets), NOT status-transition duration.

Source collection is `agent_metrics` (per-heartbeat rows, written on every
heartbeat that carries `meta.current_cpu`/`current_memory`). The
similarly-named `agent_metrics_history` collection is a capped decoy (~100
rows/agent, oldest deleted every heartbeat -> only ~25-50 minutes of retained
history) and MUST NOT be used for uptime (D-09).

No per-agent heartbeat interval is ever persisted server-side —
`interval_seconds` is a purely client-side agent config value (Rust default
15s, Python default 30s) that is never sent in any heartbeat payload. This
module therefore assumes a single FIXED 30-second expected cadence, matching
`monitor_agent_status()`'s own existing 5-min/10-missed-heartbeat assumption
(48-RESEARCH.md Pitfall 3 / Assumption A1). This is a documented
approximation, not a measured per-agent fact: a fleet running a genuinely
slower-than-30s cadence will show systematically degraded uptime %, and a
faster-than-30s fleet will show uptime naturally clipped at 100%.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

_DEFAULT_CADENCE_SECONDS = 30
_DISPLAY_BLOCK_SECONDS = 900  # 15-minute display blocks for the coarsened timeline


def _parse_timestamp(value: Any) -> Optional[datetime]:
    """Parse an agent_metrics row's ISO-8601 `timestamp` string into an aware datetime."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def compute_uptime(
    rows: List[Dict[str, Any]],
    hours: int,
    cadence_seconds: int = _DEFAULT_CADENCE_SECONDS,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Compute a heartbeat-presence uptime % + bucketed display timeline over the
    last `hours` hours from a list of `agent_metrics` rows (each with a
    `timestamp` ISO-8601 string).

    Args:
        rows: agent_metrics rows sorted or unsorted, each `{"timestamp": iso_str, ...}`.
        hours: window size in hours (caller is responsible for clamping to a
            sane range, e.g. 1..48 — this function does not enforce a ceiling).
        cadence_seconds: assumed fixed expected heartbeat interval (default 30s).
        now: reference "current time" (aware datetime); defaults to
            `datetime.now(timezone.utc)`. Exposed for deterministic testing.

    Returns:
        {
            "uptime_percent": float,   # 0.0..100.0, clipped, rounded to 1 decimal
            "expected_buckets": int,
            "received_buckets": int,
            "timeline": [ {"start": iso_str, "up": bool}, ... ],  # display-coarsened
        }

    Never raises on an empty `rows` list (never-heartbeat agent) — that case
    yields `uptime_percent == 0.0`, `received_buckets == 0`, and a `timeline`
    that is always a list (possibly all-down blocks).
    """
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    hours = max(hours, 0)
    window_start = now - timedelta(hours=hours)
    window_seconds = max((now - window_start).total_seconds(), 0)

    expected_buckets = int(window_seconds // cadence_seconds) if cadence_seconds > 0 else 0

    received_bucket_indices: Set[int] = set()
    for row in rows:
        ts = _parse_timestamp(row.get("timestamp"))
        if ts is None or ts < window_start or ts > now or cadence_seconds <= 0:
            continue
        offset = (ts - window_start).total_seconds()
        idx = int(offset // cadence_seconds)
        if 0 <= idx < expected_buckets:
            received_bucket_indices.add(idx)

    received_buckets = len(received_bucket_indices)
    if expected_buckets > 0:
        uptime_percent = round(min(received_buckets / expected_buckets, 1.0) * 100, 1)
    else:
        uptime_percent = 0.0

    timeline = _build_display_timeline(
        received_bucket_indices, window_start, expected_buckets, cadence_seconds
    )

    return {
        "uptime_percent": uptime_percent,
        "expected_buckets": expected_buckets,
        "received_buckets": received_buckets,
        "timeline": timeline,
    }


def _build_display_timeline(
    received_bucket_indices: Set[int],
    window_start: datetime,
    expected_buckets: int,
    cadence_seconds: int,
) -> List[Dict[str, Any]]:
    """
    Coarsen the fine (cadence_seconds) detection grid into readable ~15-minute
    display blocks so a near-48h window doesn't return thousands of points.
    A display block is `up` if ANY of its underlying fine buckets received a
    heartbeat. The uptime % itself is always computed on the fine grid above,
    never on this coarsened view.
    """
    if expected_buckets <= 0 or cadence_seconds <= 0:
        return []

    buckets_per_block = max(int(_DISPLAY_BLOCK_SECONDS // cadence_seconds), 1)
    timeline: List[Dict[str, Any]] = []
    idx = 0
    while idx < expected_buckets:
        block_end = min(idx + buckets_per_block, expected_buckets)
        up = any(i in received_bucket_indices for i in range(idx, block_end))
        block_start = window_start + timedelta(seconds=idx * cadence_seconds)
        timeline.append({"start": block_start.isoformat(), "up": up})
        idx = block_end

    return timeline
