from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
import ipaddress
import logging
from database import get_database

logger = logging.getLogger(__name__)

# Same window the status sweeper uses to mark an agent Offline (app_background_tasks.AGENT_OFFLINE_AFTER).
ONLINE_WITHIN = timedelta(minutes=5)
# A measured transfer rate (network_rate) older than this no longer describes current traffic.
RATE_FRESH_FOR = timedelta(minutes=5)
MAX_REMOTE_PER_ENDPOINT = 10
MAX_NEIGHBOURS = 60
HIDDEN_AGENT_STATUSES = {"Rejected", "Replaced", "Uninstalled"}

AGENT_PROJECTION = {
    "_id": 0, "id": 1, "hostname": 1, "ipAddress": 1, "platform": 1, "os": 1, "version": 1,
    "status": 1, "lastSeen": 1, "publicIp": 1, "networkRate": 1,
    "meta.metrics_collection.network.bytes_sent": 1, "meta.metrics_collection.network.bytes_recv": 1,
    "meta.network_discovery": 1, "meta.web_monitor.web_connections": 1, "meta.device_type": 1,
    "meta.mac_address": 1, "meta.os_full_name": 1,
}


def _addr(value: Any):
    try:
        return ipaddress.ip_address(str(value).strip())
    except ValueError:
        return None


def _same_24(a, b) -> bool:
    return a is not None and b is not None and a.version == b.version == 4 and a.packed[:3] == b.packed[:3]


def _lan_neighbour(addr) -> bool:
    """A unicast private address (not multicast, broadcast, loopback or link-local)."""
    return (addr is not None and addr.version == 4 and addr.is_private and not addr.is_multicast
            and not addr.is_loopback and not addr.is_link_local and addr.packed[3] not in (0, 255))


def _parse(ts: Any) -> Optional[datetime]:
    if not isinstance(ts, str):
        return None
    try:
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _neighbour_entries(discovery: Any) -> List[Dict[str, Any]]:
    """The Rust agent reports {devices: [...]} (its ARP table), the Python agent {last_scan: [...]}."""
    if not isinstance(discovery, dict):
        return []
    for key in ("devices", "last_scan"):
        entries = discovery.get(key)
        if isinstance(entries, list):
            return [e for e in entries if isinstance(e, dict) and e.get("ip")]
    return []


def _known(value: Any) -> bool:
    return value not in (None, "", "Unknown")


def build_topology(devices: List[Dict[str, Any]], agents: List[Dict[str, Any]], now: datetime) -> Dict[str, Any]:
    """Cytoscape.js elements: Internet -> gateways -> scanned devices, agent endpoints and their
    LAN neighbours, plus each online endpoint's latest outbound connections.

    Only measured values are reported; a node or link with no measurement carries no metrics.
    """
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    node_ids: set = set()
    edge_ids: set = set()

    def add_node(data: Dict[str, Any]) -> str:
        if data["id"] not in node_ids:
            node_ids.add(data["id"])
            nodes.append({"data": data})
        return data["id"]

    def add_edge(source: str, target: str, **extra: Any) -> None:
        edge_id = f"edge-{source}-{target}"
        if source == target or edge_id in edge_ids:
            return
        edge_ids.add(edge_id)
        edges.append({"data": {"id": edge_id, "source": source, "target": target, "kind": "link", **extra}})

    add_node({"id": "internet", "label": "Internet", "type": "cloud", "zone": "Internet", "role": "Gateway",
              "status": "up", "icon": "cloud", "kind": "internet"})

    def virtual_gateway() -> str:
        if "virtual-gateway" not in node_ids:
            add_node({"id": "virtual-gateway", "label": "Network Gateway", "type": "firewall", "zone": "Perimeter",
                      "role": "Gateway", "status": "up", "icon": "shield", "kind": "placeholder"})
            add_edge("internet", "virtual-gateway", kind="uplink")
        return "virtual-gateway"

    live_agents = [a for a in agents if a.get("status") not in HIDDEN_AGENT_STATUSES and a.get("id")]
    agent_ips = {a.get("ipAddress") for a in live_agents if a.get("ipAddress")}
    device_by_ip = {(d.get("ipAddress") or d.get("ip")): d for d in devices if d.get("ipAddress") or d.get("ip")}

    # 1. Gateway among the scanned devices: a .1/.254 address, or a firewall/gateway/router.
    scan_gateway_id = scan_gateway_ip = None
    for device in devices:
        ip = device.get("ipAddress") or device.get("ip") or ""
        lower_type = str(device.get("deviceType", "")).lower()
        if ip in agent_ips:
            continue
        if ip.endswith(".1") or ip.endswith(".254") or any(t in lower_type for t in ("firewall", "gateway", "router")):
            scan_gateway_id, scan_gateway_ip = device.get("id") or ip, ip
            break

    # 2. Scanned devices (an agent on the same address replaces its device node).
    for device in devices:
        ip = device.get("ipAddress") or device.get("ip")
        if not ip or ip == "127.0.0.1" or ip in agent_ips:
            continue
        device_id = device.get("id") or ip
        hostname = device.get("hostname", ip)
        device_type = device.get("deviceType") or "Unknown"
        lower_type, lower_host = str(device_type).lower(), str(hostname).lower()
        zone, role, icon = "Internal LAN", "Endpoint", "laptop"
        if device_id == scan_gateway_id:
            zone, role, icon = "Perimeter", "Gateway", "shield"
        elif "server" in lower_type or "server" in lower_host:
            role, icon = "Server", "server"
            if any(x in lower_host for x in ["web", "mail", "api", "public"]):
                zone = "DMZ"
        elif "router" in lower_type or "switch" in lower_type:
            role, icon = "Infrastructure", "layers"
        elif "printer" in lower_type or "printer" in lower_host:
            role, icon = "Peripheral", "printer"

        parent_id = f"zone-{zone.replace(' ', '-')}"
        vlan_id = device.get("vlanId")
        if vlan_id:
            vlan_node_id = f"vlan-{vlan_id}"
            add_node({"id": vlan_node_id, "label": f"VLAN {vlan_id}", "type": "subnet", "icon": "layers",
                      "isVlan": True, "vlanId": vlan_id, "parent": parent_id, "hosts": [], "kind": "vlan"})
            parent_id = vlan_node_id

        data = {"id": device_id, "label": f"{hostname}\n({ip})", "ip": ip, "type": device_type, "role": role,
                "zone": zone, "icon": icon, "status": str(device.get("status", "Up")).capitalize(),
                "parent": parent_id, "vlanId": vlan_id, "kind": "device", "details": device}
        if isinstance(device.get("metrics"), dict):
            data["metrics"] = device["metrics"]
        add_node(data)

    if scan_gateway_id in node_ids:
        add_edge("internet", scan_gateway_id, kind="uplink")
    for device in devices:
        device_id = device.get("id") or device.get("ipAddress") or device.get("ip")
        if device_id in node_ids and device_id != scan_gateway_id:
            add_edge(scan_gateway_id if scan_gateway_id in node_ids else virtual_gateway(), device_id)

    # 3. Agent endpoints, the gateway and neighbours in their neighbour (ARP) tables, and their
    #    latest outbound web connections.
    neighbour_count = 0
    for agent in live_agents:
        ip = agent.get("ipAddress")
        addr = _addr(ip)
        meta = agent.get("meta") or {}
        hostname = agent.get("hostname") or agent["id"]
        last_seen = _parse(agent.get("lastSeen"))
        online = bool(last_seen and now - last_seen <= ONLINE_WITHIN)
        device_type = str(meta.get("device_type") or "").lower()
        is_server = device_type in ("server", "virtual_machine")
        node_id = f"agent-{agent['id']}"

        metrics: Dict[str, Any] = {}
        net = (meta.get("metrics_collection") or {}).get("network") or {}
        if isinstance(net.get("bytes_sent"), (int, float)) and isinstance(net.get("bytes_recv"), (int, float)):
            metrics.update({"bytesSent": net["bytes_sent"], "bytesRecv": net["bytes_recv"]})
        rate = agent.get("networkRate") or {}
        rate_at = _parse(rate.get("at"))
        if online and rate_at and now - rate_at <= RATE_FRESH_FOR:
            metrics.update({"sentBps": rate.get("sentBps"), "recvBps": rate.get("recvBps"),
                            "rateAt": rate.get("at"), "windowSeconds": rate.get("windowSeconds")})

        scanned = device_by_ip.get(ip) or {}
        details = {
            "macAddress": meta.get("mac_address") or scanned.get("macAddress"),
            "osVersion": meta.get("os_full_name") or agent.get("os") or agent.get("platform"),
            "publicIp": agent.get("publicIp"),
            "agentVersion": agent.get("version"),
            "lastSeen": agent.get("lastSeen"),
            "openPorts": scanned.get("openPorts"),
            "vendor": scanned.get("vendor"),
        }
        add_node({"id": node_id, "label": f"{hostname}\n({ip or 'no address'})", "ip": ip,
                  "type": meta.get("device_type") or agent.get("platform") or "Endpoint",
                  "role": "Server" if is_server else "Endpoint",
                  "zone": "Internal LAN" if addr is None or addr.is_private else "DMZ",
                  "icon": "server" if is_server else "laptop", "status": "Up" if online else "Down",
                  "kind": "agent", "agentId": agent["id"], "metrics": metrics,
                  "details": {k: v for k, v in details.items() if _known(v)}})

        entries = _neighbour_entries(meta.get("network_discovery"))
        gateway_entry = next((e for e in entries if _same_24(_addr(e["ip"]), addr) and e["ip"] != ip
                              and str(e["ip"]).rsplit(".", 1)[-1] in ("1", "254")), None)
        if gateway_entry:
            gw_ip = gateway_entry["ip"]
            gateway_id = (device_by_ip.get(gw_ip) or {}).get("id") or f"gw-{gw_ip}"
            if gateway_id not in node_ids:
                gw_details = {"macAddress": gateway_entry.get("mac"), "publicIp": agent.get("publicIp"),
                              "source": f"Neighbour table of {hostname}"}
                add_node({"id": gateway_id, "label": f"Gateway\n({gw_ip})", "ip": gw_ip, "type": "router",
                          "zone": "Perimeter", "role": "Gateway", "status": "Up", "icon": "shield", "kind": "gateway",
                          "details": {k: v for k, v in gw_details.items() if _known(v)}})
            add_edge("internet", gateway_id, kind="uplink")
        elif scan_gateway_id in node_ids and (addr is None or _same_24(_addr(scan_gateway_ip), addr)):
            gateway_id = scan_gateway_id
        else:
            gateway_id = virtual_gateway()
        add_edge(gateway_id, node_id, kind="uplink", **{k: metrics[k] for k in ("sentBps", "recvBps") if k in metrics})

        for entry in entries:
            if neighbour_count >= MAX_NEIGHBOURS:
                break
            n_ip = entry["ip"]
            n_addr = _addr(n_ip)
            if n_ip in (ip,) or n_ip in agent_ips or (gateway_entry and n_ip == gateway_entry["ip"]) or not _lan_neighbour(n_addr):
                continue
            neighbour_id = (device_by_ip.get(n_ip) or {}).get("id") or f"nb-{n_ip}"
            if neighbour_id not in node_ids:
                name = entry.get("hostname") if _known(entry.get("hostname")) else n_ip
                add_node({"id": neighbour_id, "label": name if name == n_ip else f"{name}\n({n_ip})", "ip": n_ip,
                          "type": entry.get("device_type") or "Neighbour", "zone": "Internal LAN", "role": "Neighbour",
                          "status": "Up", "icon": "monitor", "kind": "neighbour",
                          "details": {k: v for k, v in {"macAddress": entry.get("mac"),
                                                         "source": f"Neighbour table of {hostname}"}.items() if _known(v)}})
                neighbour_count += 1
            add_edge(gateway_id, neighbour_id)

        if not online:
            continue  # connections an offline agent reported last are not current
        destinations: Dict[str, Dict[str, Any]] = {}
        for conn in (meta.get("web_monitor") or {}).get("web_connections") or []:
            if not isinstance(conn, dict):
                continue
            dest = conn.get("remote_host") or conn.get("remote_ip")
            if not dest:
                continue
            entry = destinations.setdefault(dest, {"ip": conn.get("remote_ip"), "count": 0, "ports": set(), "processes": set()})
            entry["count"] += 1
            if str(conn.get("port", "")).isdigit():
                entry["ports"].add(int(conn["port"]))
            if conn.get("process"):
                entry["processes"].add(str(conn["process"]))
        ranked = sorted(destinations.items(), key=lambda kv: (-kv[1]["count"], kv[0]))[:MAX_REMOTE_PER_ENDPOINT]
        for dest, info in ranked:
            remote_id = f"remote-{dest}"
            dest_addr = _addr(info["ip"])
            internal = dest_addr is not None and dest_addr.is_private
            if remote_id not in node_ids:
                add_node({"id": remote_id, "label": dest if dest == info["ip"] or not info["ip"] else f"{dest}\n({info['ip']})",
                          "ip": info["ip"], "type": "remote", "zone": "Internal LAN" if internal else "Internet",
                          "role": "Remote host", "status": "Up", "icon": "globe", "kind": "remote"})
            add_edge(node_id, remote_id, kind="flow", connections=info["count"], ports=sorted(info["ports"]),
                     processes=sorted(info["processes"])[:5], seenAt=agent.get("lastSeen"))

    # VLAN host lists for the details panel.
    for v_node in [n for n in nodes if n["data"].get("isVlan")]:
        v_id = v_node["data"]["vlanId"]
        v_hosts = [{"hostname": d.get("hostname", d.get("ip")), "ip": d.get("ipAddress") or d.get("ip"),
                    "status": d.get("status", "Up")} for d in devices if d.get("vlanId") == v_id]
        v_node["data"]["hosts"] = v_hosts
        v_node["data"]["label"] = f"VLAN {v_id}\n({len(v_hosts)} Hosts)"

    return {"elements": {"nodes": nodes, "edges": edges}, "generatedAt": now.isoformat()}


class NetworkTopologyService:
    @staticmethod
    async def get_topology_data(tenant_id: str) -> Dict[str, Any]:
        """Network topology of a tenant in Cytoscape.js JSON format (see build_topology)."""
        db = get_database()
        devices = await db.network_devices.find({"tenantId": tenant_id}, {"_id": 0}).to_list(length=1000)
        agents = await db.agents.find({"tenantId": tenant_id}, AGENT_PROJECTION).to_list(length=1000)
        return build_topology(devices, agents, datetime.now(timezone.utc))
