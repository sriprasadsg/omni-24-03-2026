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
    assert ("isp-ip-103.174.161.211", "gw-192.168.0.1") in edges  # via its provider, see the ISP tests
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
    assert ("isp-ip-103.174.161.211", "dev-gw") in edges and ("internet", "dev-gw") not in edges


def test_hidden_agents_and_empty_tenant():
    """protects=rejected/replaced/uninstalled agents stay off the map, and a tenant with nothing
    shows just the Internet; fails_when=dead agents or a stray placeholder appear; no_claim=-"""
    nodes, _ = _graph([], [_windows_agent(status="Uninstalled")])
    assert list(nodes) == ["internet"]


# ── internet provider ───────────────────────────────────────────────────────

def test_provider_named_by_the_asn_lookup_sits_between_internet_and_gateway():
    """protects=an endpoint's ISP (geo.asn from the server's ASN lookup) is one node per AS between
    the Internet and the endpoint's gateway, with its public addresses and the endpoints that report
    it; fails_when=the gateway still links straight to the Internet, endpoints on one ISP get one node
    each, or the name is invented; no_claim=the MaxMind ASN data names the right provider"""
    airtel = {"asn": {"number": 24560, "org": "Bharti Airtel Ltd."}, "city": "Chennai", "country": "India"}
    second = _windows_agent(id="a-two", hostname="FIN-WS-22", ipAddress="192.168.0.131", publicIp="103.174.161.212", geo=airtel)
    nodes, edges = _graph([], [_windows_agent(geo=airtel), second])
    isp = nodes["isp-as24560"]
    assert isp["label"] == "Bharti Airtel Ltd.\n(AS24560)" and isp["kind"] == "isp" and isp["ispKnown"] is True
    assert isp["zone"] == "Internet" and isp["status"] == "Up"
    assert isp["details"] == {"isp": "Bharti Airtel Ltd.", "asn": 24560, "location": "Chennai, India",
                              "publicIp": "103.174.161.211, 103.174.161.212", "reportedBy": "EILT0197, FIN-WS-22"}
    assert [n for n in nodes if n.startswith("isp-")] == ["isp-as24560"]
    assert ("internet", "isp-as24560") in edges and ("isp-as24560", "gw-192.168.0.1") in edges
    assert ("internet", "gw-192.168.0.1") not in edges


def test_unnamed_provider_shows_the_public_address_and_no_address_means_no_provider():
    """protects=without an ASN match the hop still shows, as "ISP not identified" with the public
    address; an endpoint that reported no public address keeps a direct gateway link and an offline
    one leaves the provider's status unknown; fails_when=a provider name is made up or a provider
    node appears with nothing behind it; no_claim=-"""
    nodes, edges = _graph([], [_windows_agent(geo={"asn": None}, lastSeen=_at(900))])
    isp = nodes["isp-ip-103.174.161.211"]
    assert isp["label"] == "ISP not identified\n(103.174.161.211)" and isp["ispKnown"] is False
    assert isp["status"] == "Unknown" and isp["ip"] == "103.174.161.211"
    assert "isp" not in isp["details"] and isp["details"]["publicIp"] == "103.174.161.211"

    nodes, edges = _graph([], [_linux_agent()])
    assert not any(n.startswith("isp-") for n in nodes)
    assert ("internet", "virtual-gateway") in edges


# ── duplicate interfaces, packets ───────────────────────────────────────────

def _win_net(sent, recv, p_sent, p_recv):
    iface = {"bytes_sent": sent, "bytes_recv": recv, "packets_sent": p_sent, "packets_recv": p_recv}
    return {"bytes_sent": 2 * sent, "bytes_recv": 2 * recv,  # what agent 2.1.19 sends: the copy counted too
            "interfaces": [{"name": "Wi-Fi", **iface}, {"name": "Wi-Fi-Npcap Packet Driver (NPCAP)-0000", **iface}]}


def test_filter_driver_copies_are_not_counted_twice_and_packets_get_a_rate():
    """protects=a Windows filter-driver interface ("<adapter>-<filter>-0000") with the adapter's own
    counters is left out of the totals, and packet counters give packets per second; fails_when=rates
    read double (live EILT0197 did) or packets are invented for agents that send none;
    no_claim=every filter driver uses that naming"""
    assert network_rate.totals(_win_net(300, 1000, 7, 12)) == {"sent": 300, "recv": 1000, "pSent": 7, "pRecv": 12}
    agent = {"networkSample": {"sent": 1_000, "recv": 5_000, "pSent": 100, "pRecv": 400, "at": _at(40)}}
    rate = network_rate.on_heartbeat(agent, _win_net(41_000, 185_000, 900, 2_400), NOW)["networkRate"]
    assert (rate["sentBps"], rate["recvBps"], rate["sentPps"], rate["recvPps"]) == (1000.0, 4500.0, 20.0, 50.0)
    linux = {"bytes_sent": 41_000, "bytes_recv": 185_000, "interfaces": [{"interface": "eth0", "mac": "x"}]}
    assert network_rate.totals(linux) == {"sent": 41_000, "recv": 185_000}
    rate = network_rate.on_heartbeat({"networkSample": {"sent": 1_000, "recv": 5_000, "at": _at(40)}}, linux, NOW)["networkRate"]
    assert "sentPps" not in rate


def test_endpoint_metrics_carry_packet_rates_and_deduplicated_totals():
    """protects=the map's endpoint metrics show packets per second and the totals without the copy;
    fails_when=the inspector shows doubled totals; no_claim=-"""
    agent = _windows_agent(networkRate={"sentBps": 9.0, "recvBps": 9.0, "sentPps": 3.0, "recvPps": 4.0, "at": _at(20)})
    agent["meta"]["metrics_collection"]["network"] = _win_net(300, 1000, 7, 12)
    nodes, _ = _graph([], [agent])
    m = nodes["agent-a-win"]["metrics"]
    assert (m["bytesSent"], m["bytesRecv"], m["sentPps"], m["recvPps"]) == (300, 1000, 3.0, 4.0)


# ── route to the server, platform node ──────────────────────────────────────

def _route(*hops, reached=True):
    return {"target": "omni.example.com", "traced_at": _at(120), "reached": reached,
            "hops": [{"hop": n, "ip": ip, "rtt_ms": rtt} for n, ip, rtt in hops]}


def test_traced_route_runs_from_the_gateway_through_each_hop_to_the_server():
    """protects=an endpoint's traced route is drawn gateway -> hop -> ... -> Omni-Agent server with each
    hop's address and round-trip time, silent hops collapsed into one node, and the path kept on the
    endpoint; fails_when=hops are missing, duplicated for endpoints sharing them, or the gateway
    appears twice; no_claim=the agent's trace itself is right"""
    route = _route((1, "192.168.0.1", 1.0), (2, "100.64.0.1", 4.2), (3, None, None), (4, None, None),
                   (5, "103.174.160.1", 9.8), (6, "57.154.210.55", 31.5))
    agent = _windows_agent()
    agent["meta"]["network_discovery"]["route"] = route
    other = _windows_agent(id="a-two", hostname="FIN-WS-22", ipAddress="192.168.0.131")
    other["meta"] = {**agent["meta"], "network_discovery": {**agent["meta"]["network_discovery"], "route": route}}
    nodes, edges = _graph([], [agent, other])
    hop = nodes["hop-100.64.0.1"]
    assert hop["kind"] == "hop" and hop["label"] == "hop 2 · 100.64.0.1\n4.2 ms" and hop["details"]["tracedBy"] == "EILT0197, FIN-WS-22"
    assert "hop-192.168.0.1" not in nodes  # hop 1 is the gateway
    assert nodes["hop-gap-a-win-3"]["label"] == "hops 3-4\nno reply"
    assert nodes["agent-a-win"]["routePath"] == ["gw-192.168.0.1", "hop-100.64.0.1", "hop-gap-a-win-3", "hop-103.174.160.1", "platform-server"]
    assert edges[("gw-192.168.0.1", "hop-100.64.0.1")]["kind"] == "route"
    assert edges[("hop-103.174.160.1", "platform-server")]["rtt"] == 31.5
    server = nodes["platform-server"]
    assert server["kind"] == "server" and ("internet", "platform-server") in edges
    assert server["details"] == {"reportingEndpoints": 2, "lastReport": _at(20), "address": "omni.example.com", "serverIp": "57.154.210.55"}


def test_unfinished_trace_ends_at_the_server_marked_unreached_and_no_route_draws_no_hops():
    """protects=a trace that stopped early still leads to the server, marked unreached; an endpoint
    without a route gets no hops but the server node still lists it; fails_when=a missing trace shows
    an invented path; no_claim=-"""
    agent = _windows_agent()
    agent["meta"]["network_discovery"]["route"] = _route((1, "192.168.0.1", 1.0), (2, "100.64.0.1", 4.0), (3, None, None), reached=False)
    nodes, edges = _graph([], [agent])
    assert edges[("hop-gap-a-win-3", "platform-server")]["unreached"] is True
    nodes, edges = _graph([], [_linux_agent()])
    assert not any(n.startswith("hop-") for n in nodes) and "routePath" not in nodes["agent-a-lin"]
    assert nodes["platform-server"]["details"]["reportingEndpoints"] == 1
