"""Network Topology map from live agent data: endpoints, their gateways and connections, and
transfer rates measured from the byte counters agents send.

Each test states its card: protects=<observable>; fails_when=<wrong result it rejects>;
no_claim=<what green does not prove>. Pure functions only: no database, no app.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import network_rate
from network_topology_service import build_topology

NOW = datetime(2026, 11, 17, 18, 0, tzinfo=timezone.utc)


def _at(seconds_ago: float) -> str:
    return (NOW - timedelta(seconds=seconds_ago)).isoformat()


# ── network_rate ────────────────────────────────────────────────────────────

def test_rate_is_measured_between_changes_of_the_counters():
    """protects=rate = byte delta / seconds between two counter changes; fails_when=the rate is taken
    between heartbeats or from one sample; no_claim=the agent's counters themselves are right."""
    agent = {"networkSample": {"sent": 1_000, "recv": 5_000, "at": _at(40)}}
    update = network_rate.on_heartbeat(agent, {"bytes_sent": 41_000, "bytes_recv": 185_000}, NOW)
    assert update["networkSample"] == {"sent": 41_000, "recv": 185_000, "at": NOW.isoformat()}
    assert update["networkRate"]["sentBps"] == 1000.0
    assert update["networkRate"]["recvBps"] == 4500.0
    assert update["networkRate"]["windowSeconds"] == 40.0


def test_resent_counters_change_nothing():
    """protects=a heartbeat repeating the last collection keeps the sample time; fails_when=it resets
    the window (rates would read 0 or jump); no_claim=-"""
    agent = {"networkSample": {"sent": 10, "recv": 20, "at": _at(30)}}
    assert network_rate.on_heartbeat(agent, {"bytes_sent": 10, "bytes_recv": 20}, NOW) == {}


def test_first_sample_restart_and_old_sample_give_no_rate():
    """protects=no rate from a first sample, a host restart (totals went down) or a 15+ min gap;
    fails_when=a negative or meaningless rate is stored; no_claim=-"""
    first = network_rate.on_heartbeat({}, {"bytes_sent": 10, "bytes_recv": 20}, NOW)
    assert "networkRate" not in first and first["networkSample"]["sent"] == 10
    restarted = {"networkSample": {"sent": 9_000, "recv": 9_000, "at": _at(30)}}
    assert "networkRate" not in network_rate.on_heartbeat(restarted, {"bytes_sent": 10, "bytes_recv": 20}, NOW)
    old = {"networkSample": {"sent": 1, "recv": 1, "at": _at(16 * 60)}}
    assert "networkRate" not in network_rate.on_heartbeat(old, {"bytes_sent": 10, "bytes_recv": 20}, NOW)
    assert network_rate.on_heartbeat({}, {"bytes_sent": "x"}, NOW) == {}


def test_counters_found_in_both_agent_shapes():
    """protects=the Python and Rust agents' network blocks are both read; fails_when=one agent never
    gets a rate; no_claim=-"""
    assert network_rate.network_counters({"metrics_collection": {"network": {"bytes_sent": 1}}}) == {"bytes_sent": 1}
    assert network_rate.network_counters({"network": {"bytes_recv": 2}}) == {"bytes_recv": 2}
    assert network_rate.network_counters(None) is None


# ── build_topology ──────────────────────────────────────────────────────────

def _windows_agent(**over):
    agent = {
        "id": "a-win", "hostname": "EILT0197", "ipAddress": "192.168.0.105", "status": "Online",
        "lastSeen": _at(20), "publicIp": "103.174.161.211",
        "networkRate": {"sentBps": 41_000.0, "recvBps": 178_000.0, "at": _at(20), "windowSeconds": 42.6},
        "meta": {
            "device_type": "laptop", "mac_address": "9c:b1:50:f4:58:12",
            "metrics_collection": {"network": {"bytes_sent": 198_048_746, "bytes_recv": 974_811_266}},
            "network_discovery": {"local_ip": "192.168.0.105", "devices": [
                {"ip": "192.168.0.1", "mac": "60-32-b1-08-ba-d6", "type": "dynamic"},
                {"ip": "192.168.0.42", "mac": "aa-bb-cc-dd-ee-ff", "type": "dynamic"},
                {"ip": "192.168.0.255", "mac": "ff-ff-ff-ff-ff-ff", "type": "static"},
                {"ip": "224.0.0.22", "mac": "01-00-5e-00-00-16", "type": "static"},
            ]},
        },
    }
    agent.update(over)
    return agent


def _linux_agent(**over):
    conn = lambda proc, ip, host, port: {"process": proc, "pid": 1, "remote_ip": ip, "remote_host": host, "port": port}
    agent = {
        "id": "a-lin", "hostname": "Omniai-copy", "ipAddress": "10.0.0.4", "status": "Online", "lastSeen": _at(10),
        "meta": {"device_type": "virtual_machine",
                 "network_discovery": {"last_scan": [{"ip": "10.0.0.4", "hostname": "omniai-copy"}]},
                 "web_monitor": {"web_connections": [
                     conn("claude", "160.79.104.10", "api.anthropic.com", 443),
                     conn("node", "160.79.104.10", "api.anthropic.com", 443),
                     conn("curl", "93.184.215.14", "example.com", 80),
                 ]}},
    }
    agent.update(over)
    return agent


def _graph(devices, agents):
    out = build_topology(devices, agents, NOW)["elements"]
    return {n["data"]["id"]: n["data"] for n in out["nodes"]}, {(e["data"]["source"], e["data"]["target"]): e["data"] for e in out["edges"]}


def test_endpoint_hangs_off_the_gateway_from_its_neighbour_table_with_its_live_rate():
    """protects=an agent is an endpoint node behind the gateway its ARP table names, and the uplink
    carries the measured rate; fails_when=endpoints are missing from the map or rates are invented;
    no_claim=the .1/.254 guess is the real default route"""
    nodes, edges = _graph([], [_windows_agent()])
    endpoint = nodes["agent-a-win"]
    assert endpoint["kind"] == "agent" and endpoint["status"] == "Up" and endpoint["ip"] == "192.168.0.105"
    assert endpoint["metrics"]["sentBps"] == 41_000.0 and endpoint["metrics"]["bytesRecv"] == 974_811_266
    assert nodes["gw-192.168.0.1"]["details"]["macAddress"] == "60-32-b1-08-ba-d6"
    assert ("internet", "gw-192.168.0.1") in edges
    uplink = edges[("gw-192.168.0.1", "agent-a-win")]
    assert uplink["kind"] == "uplink" and uplink["recvBps"] == 178_000.0
    assert ("gw-192.168.0.1", "nb-192.168.0.42") in edges  # a LAN neighbour
    assert not any(i.startswith("nb-224.") or i == "nb-192.168.0.255" for i in nodes)  # multicast/broadcast
    assert "virtual-gateway" not in nodes


def test_stale_rate_and_offline_agent_show_no_live_transfer():
    """protects=a rate older than 5 min, or from an offline agent, is not shown as live;
    fails_when=an old measurement reads as current traffic; no_claim=-"""
    nodes, edges = _graph([], [_windows_agent(networkRate={"sentBps": 9.0, "recvBps": 9.0, "at": _at(600)})])
    assert "sentBps" not in nodes["agent-a-win"]["metrics"]
    assert "sentBps" not in edges[("gw-192.168.0.1", "agent-a-win")]
    nodes, _ = _graph([], [_windows_agent(lastSeen=_at(900))])
    assert nodes["agent-a-win"]["status"] == "Down" and "sentBps" not in nodes["agent-a-win"]["metrics"]


def test_latest_outbound_connections_become_remote_hosts():
    """protects=an online endpoint's web connections show as remote hosts, one per destination with
    ports and processes; fails_when=connections are missing, duplicated or kept for an offline agent;
    no_claim=the Windows agent reports connections (it does not yet)"""
    nodes, edges = _graph([], [_linux_agent()])
    flow = edges[("agent-a-lin", "remote-api.anthropic.com")]
    assert flow["kind"] == "flow" and flow["connections"] == 2 and flow["ports"] == [443]
    assert flow["processes"] == ["claude", "node"]
    assert nodes["remote-api.anthropic.com"]["zone"] == "Internet"
    assert ("virtual-gateway", "agent-a-lin") in edges  # its table names no gateway
    nodes, edges = _graph([], [_linux_agent(lastSeen=_at(900))])
    assert not any(k[1].startswith("remote-") for k in edges)


def test_scanned_devices_carry_no_invented_metrics_and_agents_replace_their_device_node():
    """protects=a scanned device gets metrics only if it reported some, and an agent on the same IP
    is one node; fails_when=per-type default throughput comes back or a machine appears twice;
    no_claim=-"""
    devices = [
        {"id": "dev-gw", "ipAddress": "192.168.0.1", "hostname": "router", "deviceType": "Router"},
        {"id": "dev-pc", "ipAddress": "192.168.0.105", "hostname": "EILT0197", "macAddress": "x", "openPorts": [445]},
        {"id": "dev-nas", "ipAddress": "192.168.0.50", "hostname": "nas", "deviceType": "Server"},
    ]
    nodes, edges = _graph(devices, [_windows_agent()])
    assert "dev-pc" not in nodes and nodes["agent-a-win"]["details"]["openPorts"] == [445]
    assert "metrics" not in nodes["dev-nas"] and "metrics" not in nodes["internet"]
    assert ("dev-gw", "agent-a-win") in edges and "gw-192.168.0.1" not in nodes
    assert ("internet", "dev-gw") in edges


def test_hidden_agents_and_empty_tenant():
    """protects=rejected/replaced/uninstalled agents stay off the map, and a tenant with nothing
    shows just the Internet; fails_when=dead agents or a stray placeholder appear; no_claim=-"""
    nodes, _ = _graph([], [_windows_agent(status="Uninstalled")])
    assert list(nodes) == ["internet"]
