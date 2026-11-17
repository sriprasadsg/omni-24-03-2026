"""Network Operations console: live and historical transfer of a tenant's agent endpoints, their
latest outbound connections and their path to the internet, from what agents report today.

Rates come from network_rate (measured between changes of each agent's byte counters, about once
a minute) and its 48 h sample history. No agent collects latency, jitter, packet loss, per-protocol
bytes (DNS/SSH/UDP), per-connection bandwidth or packet contents yet; those are listed in
``notCollected`` so the console can say so instead of showing numbers.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from database import get_database
import network_rate
from network_topology_service import (
    AGENT_PROJECTION as _TOPOLOGY_PROJECTION, HIDDEN_AGENT_STATUSES, ONLINE_WITHIN, RATE_FRESH_FOR,
    _addr, _known, _neighbour_entries, _parse, _same_24,
)

# Range -> (seconds, bucket seconds). Buckets are at least as long as a typical measurement window
# (40-75 s), so a chart point is an average of real samples rather than a guess between them.
RANGES: Dict[str, Tuple[int, int]] = {"15m": (900, 60), "1h": (3600, 120), "6h": (21600, 600), "24h": (86400, 1800)}
# An endpoint whose next sample is late keeps its last rate for this long, then counts as no data.
HOLD_SECONDS = 90
MAX_CONNECTIONS = 500
NOT_COLLECTED = ["latency", "jitter", "packetLoss", "dnsSshUdp", "connectionBandwidth", "packetInspection"]

AGENT_PROJECTION = {**_TOPOLOGY_PROJECTION, "meta.metrics_collection.network.interfaces": 1}


def protocol_of(port: Any) -> str:
    port = int(port) if str(port).isdigit() else 0
    if port in (443, 8443):
        return "HTTPS"
    if port in (80, 8080):
        return "HTTP"
    return "Other"


def series_from_buckets(rows: List[Dict[str, Any]], buckets: int, bucket_seconds: int) -> List[Optional[Tuple[float, float]]]:
    """Per-bucket (txBps, rxBps) summed over endpoints, None where no endpoint has data.

    ``rows`` are {agentId, b, tx, rx, w}: bytes sent/received over the samples ending in bucket b
    and the seconds those samples cover, so tx / w is the endpoint's average rate in that bucket.
    """
    hold = HOLD_SECONDS // bucket_seconds
    per_agent: Dict[str, Dict[int, Tuple[float, float]]] = defaultdict(dict)
    for row in rows:
        b, w = int(row.get("b", -1)), float(row.get("w") or 0)
        if 0 <= b < buckets and w > 0:
            per_agent[row["agentId"]][b] = (float(row.get("tx") or 0) / w, float(row.get("rx") or 0) / w)
    totals: List[Optional[Tuple[float, float]]] = [None] * buckets
    for by_bucket in per_agent.values():
        last: Optional[Tuple[int, Tuple[float, float]]] = None
        for b in range(buckets):
            value = by_bucket.get(b)
            if value is not None:
                last = (b, value)
            elif last is not None and b - last[0] <= hold:
                value = last[1]
            if value is None:
                continue
            tx, rx = totals[b] or (0.0, 0.0)
            totals[b] = (tx + value[0], rx + value[1])
    return totals


def _average(points: List[Optional[Tuple[float, float]]]) -> Optional[Dict[str, float]]:
    known = [p for p in points if p is not None]
    if not known:
        return None
    return {"txBps": round(sum(p[0] for p in known) / len(known), 1), "rxBps": round(sum(p[1] for p in known) / len(known), 1)}


def _interfaces(net: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Rust agents send per-interface bytes and packets; Python agents names and MACs only."""
    out = []
    for item in net.get("interfaces") or []:
        if not isinstance(item, dict):
            continue
        entry = {"name": item.get("name") or item.get("interface"), "mac": item.get("mac")}
        for src, dst in (("bytes_sent", "bytesSent"), ("bytes_recv", "bytesRecv"),
                         ("packets_sent", "packetsSent"), ("packets_recv", "packetsRecv")):
            if isinstance(item.get(src), (int, float)):
                entry[dst] = item[src]
        if entry["name"]:
            out.append({k: v for k, v in entry.items() if _known(v)})
    return out


def build_summary(agents: List[Dict[str, Any]], rows: List[Dict[str, Any]], now: datetime,
                  range_key: str, agent_id: Optional[str] = None) -> Dict[str, Any]:
    """Console payload from the tenant's agents and the bucketed samples of [now - 2 range, now]."""
    seconds, bucket_seconds = RANGES[range_key]
    n = seconds // bucket_seconds
    start = now - timedelta(seconds=2 * seconds)
    totals = series_from_buckets(rows, 2 * n, bucket_seconds)
    previous, current = totals[:n], totals[n:]
    series = [{"t": (start + timedelta(seconds=(n + i) * bucket_seconds)).isoformat(),
               "txBps": round(p[0], 1) if p else None, "rxBps": round(p[1], 1) if p else None}
              for i, p in enumerate(current)]

    transferred: Dict[str, List[float]] = defaultdict(lambda: [0.0, 0.0])
    for row in rows:
        if int(row.get("b", -1)) >= n:
            transferred[row["agentId"]][0] += float(row.get("tx") or 0)
            transferred[row["agentId"]][1] += float(row.get("rx") or 0)

    endpoints, connections = [], []
    protocols: Dict[str, int] = {"HTTPS": 0, "HTTP": 0, "Other": 0, "Internal": 0}
    for agent in agents:
        if agent.get("status") in HIDDEN_AGENT_STATUSES or not agent.get("id"):
            continue
        if agent_id and agent["id"] != agent_id:
            continue
        meta = agent.get("meta") or {}
        ip, hostname = agent.get("ipAddress"), agent.get("hostname") or agent["id"]
        last_seen = _parse(agent.get("lastSeen"))
        online = bool(last_seen and now - last_seen <= ONLINE_WITHIN)
        rate = agent.get("networkRate") or {}
        rate_at = _parse(rate.get("at"))
        fresh = online and rate_at is not None and now - rate_at <= RATE_FRESH_FOR
        tx_bps = rate.get("sentBps") if fresh else None
        rx_bps = rate.get("recvBps") if fresh else None
        net = (meta.get("metrics_collection") or {}).get("network") or {}
        addr = _addr(ip)
        gateway = next(({"ip": e["ip"], "mac": e.get("mac")} for e in _neighbour_entries(meta.get("network_discovery"))
                        if _same_24(_addr(e["ip"]), addr) and e["ip"] != ip and str(e["ip"]).rsplit(".", 1)[-1] in ("1", "254")), None)

        agent_connections = []
        if online:
            for conn in (meta.get("web_monitor") or {}).get("web_connections") or []:
                if not isinstance(conn, dict) or not (conn.get("remote_host") or conn.get("remote_ip")):
                    continue
                dest_addr = _addr(conn.get("remote_ip"))
                internal = dest_addr is not None and dest_addr.is_private
                protocol = protocol_of(conn.get("port"))
                protocols["Internal" if internal else protocol] += 1
                agent_connections.append({
                    "agentId": agent["id"], "hostname": hostname, "sourceIp": ip,
                    "destination": conn.get("remote_host") or conn.get("remote_ip"), "destinationIp": conn.get("remote_ip"),
                    "port": int(conn["port"]) if str(conn.get("port", "")).isdigit() else None, "protocol": protocol,
                    "process": conn.get("process"), "pid": conn.get("pid"), "scope": "Internal" if internal else "External",
                })
        connections.extend(agent_connections)

        tx_bytes, rx_bytes = transferred.get(agent["id"], [0.0, 0.0])
        endpoints.append({
            "agentId": agent["id"], "hostname": hostname, "ip": ip, "platform": agent.get("platform"),
            "os": meta.get("os_full_name") or agent.get("os") or agent.get("platform"), "lastSeen": agent.get("lastSeen"),
            "status": "Down" if not online else "Live" if (tx_bps or 0) + (rx_bps or 0) > 0 else "Idle",
            "txBps": tx_bps, "rxBps": rx_bps, "rateAt": rate.get("at") if fresh else None,
            "windowSeconds": rate.get("windowSeconds") if fresh else None,
            "rangeTxBytes": round(tx_bytes), "rangeRxBytes": round(rx_bytes),
            "bytesSent": net.get("bytes_sent"), "bytesRecv": net.get("bytes_recv"),
            "gateway": gateway, "publicIp": agent.get("publicIp"), "interfaces": _interfaces(net),
            "connections": len(agent_connections),
        })

    endpoints.sort(key=lambda e: -((e["txBps"] or 0) + (e["rxBps"] or 0)))
    measured = [e for e in endpoints if e["txBps"] is not None]
    return {
        "generatedAt": now.isoformat(), "range": range_key, "rangeSeconds": seconds, "bucketSeconds": bucket_seconds,
        "series": series,
        "current": {"txBps": round(sum(e["txBps"] for e in measured), 1), "rxBps": round(sum(e["rxBps"] for e in measured), 1),
                    "measured": len(measured), "online": sum(1 for e in endpoints if e["status"] != "Down"),
                    "endpoints": len(endpoints)},
        "average": _average(current), "previousAverage": _average(previous),
        "endpoints": endpoints, "connections": connections[:MAX_CONNECTIONS],
        "protocols": [{"name": k, "connections": v} for k, v in protocols.items()],
        "notCollected": NOT_COLLECTED,
    }


async def traffic_summary(tenant_id: str, range_key: str, agent_id: Optional[str] = None) -> Dict[str, Any]:
    db = get_database()
    seconds, bucket_seconds = RANGES[range_key]
    now = datetime.now(timezone.utc)
    start = now - timedelta(seconds=2 * seconds)
    agents = await db.agents.find({"tenantId": tenant_id}, AGENT_PROJECTION).to_list(length=1000)
    match: Dict[str, Any] = {"tenantId": tenant_id, "at": {"$gte": start, "$lte": now}}
    if agent_id:
        match["agentId"] = agent_id
    # One row per endpoint per bucket: what the samples ending in it moved, and the seconds they cover.
    pipeline = [
        {"$match": match},
        {"$project": {"agentId": 1, "w": {"$ifNull": ["$windowSeconds", 0]},
                      "tx": {"$ifNull": ["$sentBps", 0]}, "rx": {"$ifNull": ["$recvBps", 0]},
                      "b": {"$floor": {"$divide": [{"$subtract": ["$at", start]}, bucket_seconds * 1000]}}}},
        {"$group": {"_id": {"a": "$agentId", "b": "$b"}, "w": {"$sum": "$w"},
                    "tx": {"$sum": {"$multiply": ["$tx", "$w"]}}, "rx": {"$sum": {"$multiply": ["$rx", "$w"]}}}},
    ]
    rows = [{"agentId": r["_id"]["a"], "b": r["_id"]["b"], "w": r["w"], "tx": r["tx"], "rx": r["rx"]}
            async for r in db[network_rate.SAMPLES_COLLECTION].aggregate(pipeline)]
    return build_summary(agents, rows, now, range_key, agent_id)
