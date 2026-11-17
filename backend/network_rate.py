"""Live network transfer rates from the byte counters agents send on every heartbeat.

Agents send running totals (bytes sent/received since the host started), re-collected on the
metrics interval, so the same totals usually arrive on several heartbeats in a row. A rate is
therefore measured between two *changes* of the totals, not between two heartbeats:

    agent.networkSample = {sent, recv, pSent?, pRecv?, at}   totals as last changed, and when
    agent.networkRate   = {sentBps, recvBps, sentPps?, recvPps?, at, windowSeconds}

Packet rates come along when the agent reports packet counters (the Windows agent per interface).
Windows lists a filter driver bound to an adapter (Npcap, QoS, WFP) as a second interface named
"<adapter>-<filter>-0000" with the adapter's own counters; those copies are left out of the totals.
"""
from datetime import datetime
from typing import Any, Dict, Optional

# Two samples further apart than this say little about the current rate.
MAX_WINDOW_SECONDS = 15 * 60

# Every measured rate is also kept as a sample for the Network Operations history: one document per
# agent per counter change (about one a minute), dropped by a TTL index after two days (a 24 h range
# plus the 24 h before it, for the "vs previous period" delta).
SAMPLES_COLLECTION = "network_rate_samples"
SAMPLE_TTL_SECONDS = 2 * 24 * 3600
_sample_indexes_created = False


async def record_sample(db, tenant_id: str, agent_id: str, hostname: Optional[str], rate: Dict[str, Any]) -> None:
    """Store one measured rate (the networkRate fields) as a history sample."""
    global _sample_indexes_created
    at = _parse(rate.get("at"))
    if at is None or not tenant_id:
        return
    if not _sample_indexes_created:
        await db._db[SAMPLES_COLLECTION].create_index("at", expireAfterSeconds=SAMPLE_TTL_SECONDS)
        await db._db[SAMPLES_COLLECTION].create_index([("tenantId", 1), ("at", 1)])
        _sample_indexes_created = True
    await db[SAMPLES_COLLECTION].insert_one({
        "tenantId": tenant_id, "agentId": agent_id, "hostname": hostname, "at": at,
        "sentBps": rate.get("sentBps"), "recvBps": rate.get("recvBps"), "windowSeconds": rate.get("windowSeconds"),
    })


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


def _adapters(net: Dict[str, Any]) -> list:
    """Interfaces that report counters, without the filter-driver copies of another adapter."""
    ifaces = [i for i in net.get("interfaces") or [] if isinstance(i, dict) and isinstance(i.get("name"), str)]
    names = [i["name"] for i in ifaces]
    return [i for i in ifaces if not any(i["name"].startswith(f"{other}-") for other in names if other != i["name"])]


def totals(net: Optional[Dict[str, Any]]) -> Optional[Dict[str, int]]:
    """Bytes (and packets, when reported) sent and received since the host started. Taken from the
    interfaces when they carry byte counters, so filter-driver copies are not counted twice."""
    if not net:
        return None
    adapters = [i for i in _adapters(net) if _counter(i, "bytes_sent") is not None and _counter(i, "bytes_recv") is not None]
    if adapters:
        out = {"sent": sum(_counter(i, "bytes_sent") for i in adapters), "recv": sum(_counter(i, "bytes_recv") for i in adapters)}
        if all(_counter(i, "packets_sent") is not None and _counter(i, "packets_recv") is not None for i in adapters):
            out["pSent"] = sum(_counter(i, "packets_sent") for i in adapters)
            out["pRecv"] = sum(_counter(i, "packets_recv") for i in adapters)
        return out
    sent, recv = _counter(net, "bytes_sent"), _counter(net, "bytes_recv")
    if sent is None or recv is None:
        return None
    out = {"sent": sent, "recv": recv}
    p_sent, p_recv = _counter(net, "packets_sent"), _counter(net, "packets_recv")
    if p_sent is not None and p_recv is not None:
        out.update({"pSent": p_sent, "pRecv": p_recv})
    return out


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
    now_totals = totals(net)
    if now_totals is None:
        return {}
    sent, recv = now_totals["sent"], now_totals["recv"]
    prev = (agent or {}).get("networkSample") or {}
    if prev.get("sent") == sent and prev.get("recv") == recv:
        return {}  # the same collection sent again
    update: Dict[str, Any] = {"networkSample": {**now_totals, "at": now.isoformat()}}
    prev_at = _parse(prev.get("at"))
    prev_sent, prev_recv = prev.get("sent"), prev.get("recv")
    if prev_at is None or not isinstance(prev_sent, int) or not isinstance(prev_recv, int):
        return update
    elapsed = (now - prev_at).total_seconds()
    # Totals that went down mean the host restarted (or, once, that duplicate interfaces stopped
    # being counted): start over from this sample.
    if 0 < elapsed <= MAX_WINDOW_SECONDS and sent >= prev_sent and recv >= prev_recv:
        rate = {
            "sentBps": round((sent - prev_sent) / elapsed, 1),
            "recvBps": round((recv - prev_recv) / elapsed, 1),
            "at": now.isoformat(),
            "windowSeconds": round(elapsed, 1),
        }
        p_sent, p_recv, pp_sent, pp_recv = now_totals.get("pSent"), now_totals.get("pRecv"), prev.get("pSent"), prev.get("pRecv")
        if all(isinstance(v, int) for v in (p_sent, p_recv, pp_sent, pp_recv)) and p_sent >= pp_sent and p_recv >= pp_recv:
            rate["sentPps"] = round((p_sent - pp_sent) / elapsed, 1)
            rate["recvPps"] = round((p_recv - pp_recv) / elapsed, 1)
        update["networkRate"] = rate
    return update
