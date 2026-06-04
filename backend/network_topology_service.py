from typing import Dict, Any
import logging
from database import get_database
from server_discovery import ServerDiscovery

# Deterministic default metrics keyed by device type (no random values)
_DEVICE_METRICS = {
    "router":     {"throughput_in": 42.0, "throughput_out": 18.0, "latency": 1.2, "activeSessions": 80},
    "firewall":   {"throughput_in": 35.0, "throughput_out": 15.0, "latency": 0.8, "activeSessions": 60},
    "gateway":    {"throughput_in": 48.0, "throughput_out": 20.0, "latency": 1.0, "activeSessions": 90},
    "switch":     {"throughput_in": 20.0, "throughput_out": 10.0, "latency": 0.3, "activeSessions": 40},
    "server":     {"throughput_in": 8.0,  "throughput_out": 5.0,  "latency": 2.0, "activeSessions": 25},
    "workstation":{"throughput_in": 2.0,  "throughput_out": 1.0,  "latency": 3.0, "activeSessions": 5},
    "printer":    {"throughput_in": 0.5,  "throughput_out": 0.2,  "latency": 5.0, "activeSessions": 2},
}
_DEVICE_METRICS_DEFAULT = {"throughput_in": 5.0, "throughput_out": 2.0, "latency": 2.5, "activeSessions": 10}

def _default_metrics(device_type: str) -> Dict:
    return _DEVICE_METRICS.get((device_type or "").lower(), _DEVICE_METRICS_DEFAULT)

logger = logging.getLogger(__name__)

class NetworkTopologyService:
    @staticmethod
    async def get_topology_data(tenant_id: str) -> Dict[str, Any]:
        """
        Generate enterprise-grade network topology data in Cytoscape.js JSON format.
        Enforces zones: Internet -> Firewall/Gateway -> LAN.
        """
        db = get_database()
        
        # Fetch all devices for the tenant
        devices = await db.network_devices.find({"tenantId": tenant_id}, {"_id": 0}).to_list(length=1000)
        
        nodes = []
        edges = []
        
        # 0. Fetch Real ISP (Public) IP
        isp_ip = ServerDiscovery.get_public_ip()
        
        # 1. Mandatory Infrastructure: Internet
        nodes.append({
            "data": {
                "id": "internet",
                "label": f"Internet (External)\n{isp_ip}",
                "type": "cloud",
                "zone": "Internet",
                "role": "Gateway",
                "status": "up",
                "icon": "cloud",
                "ip": isp_ip,
                "metrics": {"throughput_in": 1200, "throughput_out": 850, "latency": 25, "activeSessions": 500}
            }
        })

        # 2. Identify Gateway/Firewall from real devices
        gateway_node_id = None
        
        # Look for a .1 or .254 IP, or a device typed as Firewall/Gateway/Router
        for device in devices:
            ip = device.get("ipAddress") or device.get("ip", "")
            lower_type = str(device.get("deviceType", "")).lower()
            if ip.endswith(".1") or ip.endswith(".254") or "firewall" in lower_type or "gateway" in lower_type or "router" in lower_type:
                gateway_node_id = device.get("id") or ip
                break
        
        # Fallback if no gateway detected
        if not gateway_node_id:
            # Create a virtual gateway if none found in scan
            gateway_node_id = "virtual-gateway"
            nodes.append({
                "data": {
                    "id": gateway_node_id,
                    "label": "Network Gateway",
                    "type": "firewall",
                    "zone": "Perimeter",
                    "role": "Gateway",
                    "status": "up",
                    "icon": "shield",
                    "ip": "Auto-Detecting...",
                    "metrics": {"throughput_in": 10, "throughput_out": 8, "latency": 1, "activeSessions": 50}
                }
            })
        
        # Connect Internet to Gateway
        edges.append({
            "data": {
                "id": f"edge-internet-{gateway_node_id}",
                "source": "internet",
                "target": gateway_node_id,
                "bandwidth": "1Gbps",
                "latency": "25ms"
            }
        })
        
        # 3. Process All Devices
        for device in devices:
            ip = device.get("ipAddress") or device.get("ip")
            if not ip or ip == "127.0.0.1":
                continue
                
            device_id = device.get("id") or ip
            hostname = device.get("hostname", ip)
            device_type = device.get("deviceType") or "Unknown"
            status = device.get("status", "Up").capitalize()
            
            # Zoning Logic
            zone = "Internal LAN"
            role = "Endpoint"
            icon = "laptop"
            
            lower_type = str(device_type).lower()
            lower_host = str(hostname).lower()
            
            if ip == gateway_node_id or device_id == gateway_node_id:
                zone = "Perimeter"
                role = "Gateway"
                icon = "shield"
            elif "server" in lower_type or "server" in lower_host:
                role = "Server"
                icon = "server"
                if any(x in lower_host for x in ["web", "mail", "api", "public"]):
                    zone = "DMZ"
            elif "router" in lower_type or "switch" in lower_type:
                role = "Infrastructure"
                icon = "layers"
            elif "printer" in lower_type or "printer" in lower_host:
                role = "Peripheral"
                icon = "printer"
            
            # 4. VLAN Parent Logic & Additional Connections
            vlan_id = device.get("vlanId")
            parent_id = f"zone-{zone.replace(' ', '-')}"
            
            if vlan_id:
                vlan_node_id = f"vlan-{vlan_id}"
                # Create VLAN parent if it doesn't exist
                if not any(n["data"]["id"] == vlan_node_id for n in nodes):
                    nodes.append({
                        "data": {
                            "id": vlan_node_id,
                            "label": f"VLAN {vlan_id}",
                            "type": "subnet",
                            "icon": "layers",
                            "isVlan": True,
                            "vlanId": vlan_id,
                            "parent": parent_id,
                            "hosts": [] # Will populate in second pass/refactor
                        }
                    })
                parent_id = vlan_node_id

            # Add Node with dynamic parent (Zone or VLAN)
            nodes.append({
                "data": {
                    "id": device_id,
                    "label": f"{hostname}\n({ip})",
                    "ip": ip,
                    "type": device_type,
                    "role": role,
                    "zone": zone,
                    "icon": icon,
                    "status": status,
                    "parent": parent_id,
                    "vlanId": vlan_id,
                    "metrics": device.get("metrics", _default_metrics(device_type)),
                    "details": device
                }
            })
            
            # Connect to Gateway (if not the gateway itself)
            if device_id != gateway_node_id:
                edges.append({
                    "data": {
                        "id": f"edge-{gateway_node_id}-{device_id}",
                        "source": gateway_node_id,
                        "target": device_id,
                        "bandwidth": "1Gbps",
                        "latency": "1ms"
                    }
                })
        
        # 5. Populate host lists in VLAN nodes for the UI
        for v_node in [n for n in nodes if n["data"].get("isVlan")]:
            v_id = v_node["data"]["vlanId"]
            v_hosts = []
            for d in devices:
                if d.get("vlanId") == v_id:
                    v_hosts.append({
                        "hostname": d.get("hostname", d.get("ip")),
                        "ip": d.get("ipAddress") or d.get("ip"),
                        "status": d.get("status", "Up")
                    })
            v_node["data"]["hosts"] = v_hosts
            v_node["data"]["label"] = f"VLAN {v_id}\n({len(v_hosts)} Hosts)"
            
        return {
            "elements": {
                "nodes": nodes,
                "edges": edges
            }
        }
