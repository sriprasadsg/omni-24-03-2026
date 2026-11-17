"""Live network transfer rates from the byte counters agents send on every heartbeat.

Agents send running totals (bytes sent/received since the host started), re-collected on the
metrics interval, so the same totals usually arrive on several heartbeats in a row. A rate is
therefore measured between two *changes* of the totals, not between two heartbeats:

    agent.networkSample = {sent, recv, at}            totals as last changed, and when
    agent.networkRate   = {sentBps, recvBps, at, windowSeconds}
"""
from datetime import datetime
from typing import Any, Dict, Optional

# Two samples further apart than this say little about the current rate.
MAX_WINDOW_SECONDS = 15 * 60


def _counter(net: Dict[str, Any], key: str) -> Optional[int]:
    value = net.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return int(value)


def network_counters(meta: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The network block of a heartbeat's meta (both agents nest it under metrics_collection)."""
    if not isinstance(meta, dict):
        return None
    metrics = meta.get("metrics_collection")
    net = metrics.get("network") if isinstance(metrics, dict) else None
    if not isinstance(net, dict):
        net = meta.get("network")
    return net if isinstance(net, dict) else None


def _parse(ts: Any) -> Optional[datetime]:
    if not isinstance(ts, str):
        return None
    try:
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


def on_heartbeat(agent: Optional[Dict[str, Any]], net: Optional[Dict[str, Any]], now: datetime) -> Dict[str, Any]:
    """Fields to $set on the agent for this heartbeat's counters ({} when nothing changed)."""
    if not net:
        return {}
    sent, recv = _counter(net, "bytes_sent"), _counter(net, "bytes_recv")
    if sent is None or recv is None:
        return {}
    prev = (agent or {}).get("networkSample") or {}
    if prev.get("sent") == sent and prev.get("recv") == recv:
        return {}  # the same collection sent again
    update: Dict[str, Any] = {"networkSample": {"sent": sent, "recv": recv, "at": now.isoformat()}}
    prev_at = _parse(prev.get("at"))
    prev_sent, prev_recv = prev.get("sent"), prev.get("recv")
    if prev_at is None or not isinstance(prev_sent, int) or not isinstance(prev_recv, int):
        return update
    elapsed = (now - prev_at).total_seconds()
    # Totals that went down mean the host restarted: start over from this sample.
    if 0 < elapsed <= MAX_WINDOW_SECONDS and sent >= prev_sent and recv >= prev_recv:
        update["networkRate"] = {
            "sentBps": round((sent - prev_sent) / elapsed, 1),
            "recvBps": round((recv - prev_recv) / elapsed, 1),
            "at": now.isoformat(),
            "windowSeconds": round(elapsed, 1),
        }
    return update
