"""Network Operations console data (network_ops_service) and the rate history behind it.

Each test states its card: protects=<observable>; fails_when=<wrong result it rejects>;
no_claim=<what green does not prove>. Pure functions and a fake database: no MongoDB, no app.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import network_rate
from network_ops_service import RANGES, build_summary, protocol_of, series_from_buckets

NOW = datetime(2026, 11, 17, 18, 0, tzinfo=timezone.utc)


def _at(seconds_ago: float) -> str:
    return (NOW - timedelta(seconds=seconds_ago)).isoformat()


def test_buckets_sum_endpoints_and_bridge_one_late_sample():
    """protects=a bucket's value is the sum of each endpoint's average rate (bytes / covered seconds),
    a single missing bucket keeps the endpoint's last rate, a longer gap is no data; fails_when=late
    samples read as zero traffic or an offline endpoint is held for minutes; no_claim=-"""
    rows = [
        {"agentId": "a", "b": 0, "tx": 6000, "rx": 12000, "w": 60},   # 100 / 200 B/s
        {"agentId": "b", "b": 0, "tx": 3000, "rx": 0, "w": 30},       # 100 / 0 B/s
        {"agentId": "a", "b": 2, "tx": 600, "rx": 600, "w": 60},
    ]
    totals = series_from_buckets(rows, 5, 60)  # hold = 90 // 60 = 1 bucket
    assert totals[0] == (200.0, 200.0)
    assert totals[1] == (200.0, 200.0)  # both endpoints held one bucket
    assert totals[2] == (10.0, 10.0)    # b's gap is longer than the hold
    assert totals[3] == (10.0, 10.0)
    assert totals[4] is None
    assert series_from_buckets([{"agentId": "a", "b": 0, "tx": 1, "rx": 1, "w": 60}], 3, 1800)[1] is None  # 30 min buckets hold nothing


def test_protocol_comes_from_the_port():
    """protects=443/8443 are HTTPS, 80/8080 HTTP, anything else Other; fails_when=-; no_claim=the port
    alone proves the protocol"""
    assert [protocol_of(p) for p in (443, "8443", 80, 8080, 22, None)] == ["HTTPS", "HTTPS", "HTTP", "HTTP", "Other", "Other"]


def _agents():
    windows = {
        "id": "a-win", "hostname": "EILT0197", "ipAddress": "192.168.0.105", "status": "Online", "lastSeen": _at(20),
        "publicIp": "103.174.161.211", "platform": "Windows",
        "networkRate": {"sentBps": 35_000.0, "recvBps": 174_000.0, "at": _at(20), "windowSeconds": 42.1},
        "meta": {"metrics_collection": {"network": {"bytes_sent": 10, "bytes_recv": 20, "interfaces": [
                     {"name": "Wi-Fi", "bytes_sent": 5, "bytes_recv": 6, "packets_sent": 7, "packets_recv": 8}]}},
                 "network_discovery": {"devices": [{"ip": "192.168.0.1", "mac": "60-32-b1-08-ba-d6"}]}},
    }
    linux = {
        "id": "a-lin", "hostname": "Omniai-copy", "ipAddress": "10.0.0.4", "status": "Online", "lastSeen": _at(10),
        "networkRate": {"sentBps": 0.0, "recvBps": 0.0, "at": _at(10), "windowSeconds": 60},
        "meta": {"metrics_collection": {"network": {"interfaces": [{"interface": "eth0", "mac": "00:0d"}]}},
                 "web_monitor": {"web_connections": [
                     {"process": "claude", "pid": 1, "remote_ip": "160.79.104.10", "remote_host": "api.anthropic.com", "port": 443},
                     {"process": "curl", "pid": 2, "remote_ip": "93.184.215.14", "remote_host": "example.com", "port": 80},
                     {"process": "nginx", "pid": 3, "remote_ip": "10.0.0.12", "remote_host": "10.0.0.12", "port": 8080},
                 ]}},
    }
    offline = {"id": "a-old", "hostname": "OLD-PC", "ipAddress": "192.168.0.50", "status": "Offline", "lastSeen": _at(3600),
               "networkRate": {"sentBps": 9e9, "recvBps": 9e9, "at": _at(3600)}}
    gone = {"id": "a-gone", "hostname": "GONE", "status": "Uninstalled", "lastSeen": _at(10)}
    return [linux, windows, offline, gone]


def test_summary_reports_measured_rates_statuses_and_latest_connections():
    """protects=only fresh rates of online endpoints count, statuses are Live/Idle/Down, connections and
    the protocol counts come from the endpoints' last report, the gateway from their neighbour table;
    fails_when=an old or offline rate is summed, uninstalled agents appear, or numbers are invented;
    no_claim=the agents' own counters are right"""
    seconds, bucket = RANGES["1h"]
    n = seconds // bucket
    rows = [{"agentId": "a-win", "b": n + 1, "tx": 35_000 * 42, "rx": 174_000 * 42, "w": 42},
            {"agentId": "a-win", "b": 0, "tx": 1_000 * 60, "rx": 2_000 * 60, "w": 60}]
    out = build_summary(_agents(), rows, NOW, "1h")
    by_id = {e["agentId"]: e for e in out["endpoints"]}
    assert set(by_id) == {"a-win", "a-lin", "a-old"}
    assert [e["agentId"] for e in out["endpoints"]][0] == "a-win"  # busiest first
    assert by_id["a-win"]["status"] == "Live" and by_id["a-lin"]["status"] == "Idle" and by_id["a-old"]["status"] == "Down"
    assert by_id["a-old"]["txBps"] is None
    assert out["current"] == {"txBps": 35_000.0, "rxBps": 174_000.0, "measured": 2, "online": 2, "endpoints": 3}
    assert by_id["a-win"]["gateway"] == {"ip": "192.168.0.1", "mac": "60-32-b1-08-ba-d6"}
    assert by_id["a-win"]["interfaces"] == [{"name": "Wi-Fi", "bytesSent": 5, "bytesRecv": 6, "packetsSent": 7, "packetsRecv": 8}]
    assert by_id["a-lin"]["interfaces"] == [{"name": "eth0", "mac": "00:0d"}]
    assert by_id["a-win"]["rangeTxBytes"] == 35_000 * 42  # the previous-period row is not counted
    assert {c["destination"]: (c["protocol"], c["scope"]) for c in out["connections"]} == {
        "api.anthropic.com": ("HTTPS", "External"), "example.com": ("HTTP", "External"), "10.0.0.12": ("HTTP", "Internal")}
    assert {p["name"]: p["connections"] for p in out["protocols"]} == {"HTTPS": 1, "HTTP": 1, "Other": 0, "Internal": 1}
    assert "latency" in out["notCollected"] and "packetLoss" in out["notCollected"]


def test_series_covers_the_range_and_compares_with_the_period_before():
    """protects=the series is the current range only, with averages for it and for the range before;
    fails_when=the previous period leaks into the chart or the delta compares the wrong windows;
    no_claim=-"""
    seconds, bucket = RANGES["15m"]
    n = seconds // bucket
    rows = [{"agentId": "a-win", "b": 0, "tx": 100 * 60, "rx": 100 * 60, "w": 60},
            {"agentId": "a-win", "b": n + 3, "tx": 300 * 60, "rx": 500 * 60, "w": 60}]
    out = build_summary(_agents(), rows, NOW, "15m")
    assert len(out["series"]) == n and out["bucketSeconds"] == 60
    assert out["series"][3] == {"t": (NOW - timedelta(seconds=seconds) + timedelta(seconds=180)).isoformat(), "txBps": 300.0, "rxBps": 500.0}
    assert out["series"][0]["txBps"] is None
    assert out["average"] == {"txBps": 300.0, "rxBps": 500.0}
    assert out["previousAverage"] == {"txBps": 100.0, "rxBps": 100.0}


def test_endpoint_filter_keeps_one_endpoint():
    """protects=?agentId narrows the endpoints and connections to that endpoint; fails_when=other
    endpoints' rates leak into the drawer; no_claim=-"""
    out = build_summary(_agents(), [], NOW, "1h", agent_id="a-lin")
    assert [e["agentId"] for e in out["endpoints"]] == ["a-lin"] and len(out["connections"]) == 3
    assert out["current"]["txBps"] == 0.0 and out["average"] is None


def test_record_sample_creates_the_ttl_index_once_and_stores_the_rate():
    """protects=history samples expire after two days and carry tenant, agent and rate; fails_when=the
    collection grows forever or samples lose their tenant; no_claim=MongoDB enforces the TTL"""
    network_rate._sample_indexes_created = False
    raw = MagicMock()
    raw.__getitem__.return_value.create_index = AsyncMock()
    collection = MagicMock(insert_one=AsyncMock())
    db = MagicMock(_db=raw)
    db.__getitem__.return_value = collection
    rate = {"sentBps": 1.0, "recvBps": 2.0, "at": NOW.isoformat(), "windowSeconds": 40.0}
    asyncio.run(network_rate.record_sample(db, "t1", "a1", "host", rate))
    asyncio.run(network_rate.record_sample(db, "t1", "a1", "host", rate))
    index_calls = raw.__getitem__.return_value.create_index.await_args_list
    assert len(index_calls) == 2  # TTL + (tenantId, at), created on the first sample only
    assert index_calls[0].kwargs == {"expireAfterSeconds": network_rate.SAMPLE_TTL_SECONDS}
    stored = collection.insert_one.await_args.args[0]
    assert stored == {"tenantId": "t1", "agentId": "a1", "hostname": "host", "at": NOW,
                      "sentBps": 1.0, "recvBps": 2.0, "windowSeconds": 40.0}
    asyncio.run(network_rate.record_sample(db, "", "a1", "host", rate))
    assert collection.insert_one.await_count == 2  # no tenant, nothing stored
