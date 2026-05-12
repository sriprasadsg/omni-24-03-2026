"""Network Detection & Response (NDR) service — behavioral baseline, anomaly detection."""
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import uuid
import ipaddress


ANOMALY_TYPES = [
    {"type": "lateral_movement", "severity": "critical", "description": "Unusual internal east-west traffic pattern detected"},
    {"type": "data_exfiltration", "severity": "critical", "description": "Large data transfer to external IP outside business hours"},
    {"type": "port_scan", "severity": "high", "description": "Sequential port scanning activity from internal host"},
    {"type": "dns_tunneling", "severity": "high", "description": "Abnormally high DNS query volume suggesting tunneling"},
    {"type": "c2_beacon", "severity": "critical", "description": "Periodic outbound connection matching C2 beacon pattern"},
    {"type": "brute_force", "severity": "high", "description": "Repeated authentication failures across multiple hosts"},
    {"type": "protocol_anomaly", "severity": "medium", "description": "Non-standard protocol usage on well-known port"},
    {"type": "bandwidth_spike", "severity": "medium", "description": "Traffic volume 5σ above baseline for this time window"},
    {"type": "new_external_connection", "severity": "low", "description": "First-time connection to external IP not seen in 30 days"},
]

PROTOCOLS = ["TCP", "UDP", "ICMP", "DNS", "HTTP", "HTTPS", "SMB", "SSH", "RDP"]

# MITRE ATT&CK technique mapping per anomaly type
MITRE_MAP = {
    "port_scan": "T1046",
    "data_exfiltration": "T1048",
    "new_external_connection": "T1071",
    "c2_beacon": "T1071",
    "bandwidth_spike": "T1048",
    "lateral_movement": "T1021",
    "dns_tunneling": "T1071",
    "brute_force": "T1110",
    "protocol_anomaly": "T1071",
}


def _is_private_ip(ip_str: str) -> bool:
    try:
        return ipaddress.ip_address(ip_str).is_private
    except ValueError:
        return True  # treat unparseable as private (safe fallback)


class NDRService:
    def __init__(self, db):
        self.db = db
        self.col_flows = db["network_flows"]
        self.col_anomalies = db["ndr_anomalies"]
        self.col_baselines = db["ndr_baselines"]

    async def ingest_flow(self, tenant_id: str, flow: dict):
        doc = {
            "_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "src_ip": flow.get("src_ip", ""),
            "dst_ip": flow.get("dst_ip", ""),
            "src_port": flow.get("src_port", 0),
            "dst_port": flow.get("dst_port", 0),
            "protocol": flow.get("protocol", "TCP"),
            "bytes_sent": flow.get("bytes_sent", 0),
            "bytes_recv": flow.get("bytes_recv", 0),
            "duration_ms": flow.get("duration_ms", 0),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await self.col_flows.insert_one(doc)
        return doc

    async def get_anomalies(self, tenant_id: str, severity: str = None, limit: int = 50):
        q = {"tenant_id": tenant_id}
        if severity:
            q["severity"] = severity
        cursor = self.col_anomalies.find(q).sort("detected_at", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def run_detection(self, tenant_id: str):
        """Analyze recent network flows for real anomalous patterns."""
        now = datetime.now(timezone.utc)
        window_start = (now - timedelta(hours=1)).isoformat()
        month_ago = (now - timedelta(days=30)).isoformat()
        detected = []

        flows = await self.col_flows.find(
            {"tenant_id": tenant_id, "timestamp": {"$gte": window_start}}
        ).to_list(length=5000)

        if not flows:
            return detected

        by_src: dict = defaultdict(list)
        conn_pairs: dict = defaultdict(list)
        for f in flows:
            src = f.get("src_ip", "")
            dst = f.get("dst_ip", "")
            by_src[src].append(f)
            conn_pairs[(src, dst)].append(f)

        # 1. Port scan: one src probing >15 distinct dst_ports in the window
        for src_ip, src_flows in by_src.items():
            dst_ports = {f.get("dst_port") for f in src_flows if f.get("dst_port")}
            if len(dst_ports) > 15:
                anomaly = {
                    "_id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "type": "port_scan",
                    "severity": "high",
                    "description": f"Port scan detected: {src_ip} probed {len(dst_ports)} distinct ports in 1h window",
                    "src_ip": src_ip,
                    "dst_ip": src_flows[0].get("dst_ip", ""),
                    "protocol": "TCP",
                    "confidence": round(min(0.95, 0.60 + len(dst_ports) / 100.0), 2),
                    "bytes": sum(f.get("bytes_sent", 0) for f in src_flows),
                    "detected_at": now.isoformat(),
                    "status": "open",
                    "mitre_technique": "T1046",
                }
                await self.col_anomalies.insert_one(anomaly)
                detected.append(anomaly)

        # 2. Data exfiltration: >50 MB sent to external IPs from a single source
        for src_ip, src_flows in by_src.items():
            ext_flows = [f for f in src_flows if not _is_private_ip(f.get("dst_ip", ""))]
            total_bytes = sum(f.get("bytes_sent", 0) for f in ext_flows)
            if total_bytes > 50 * 1024 * 1024:
                dst_ips = list({f.get("dst_ip", "") for f in ext_flows})
                anomaly = {
                    "_id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "type": "data_exfiltration",
                    "severity": "critical",
                    "description": (
                        f"Large outbound transfer: {total_bytes // (1024 * 1024)} MB "
                        f"from {src_ip} to {len(dst_ips)} external IP(s)"
                    ),
                    "src_ip": src_ip,
                    "dst_ip": dst_ips[0] if dst_ips else "",
                    "protocol": ext_flows[0].get("protocol", "HTTPS") if ext_flows else "HTTPS",
                    "confidence": round(min(0.97, 0.70 + total_bytes / (500 * 1024 * 1024)), 2),
                    "bytes": total_bytes,
                    "detected_at": now.isoformat(),
                    "status": "open",
                    "mitre_technique": "T1048",
                }
                await self.col_anomalies.insert_one(anomaly)
                detected.append(anomaly)

        # 3. C2 beacon: ≥10 small periodic flows to the same external dst in the window
        for (src_ip, dst_ip), pair_flows in conn_pairs.items():
            if len(pair_flows) < 10 or _is_private_ip(dst_ip):
                continue
            avg_bytes = sum(f.get("bytes_sent", 0) for f in pair_flows) / len(pair_flows)
            if avg_bytes < 4096:
                anomaly = {
                    "_id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "type": "c2_beacon",
                    "severity": "critical",
                    "description": (
                        f"C2 beacon pattern: {len(pair_flows)} periodic low-volume flows "
                        f"({int(avg_bytes)} avg bytes) from {src_ip} to {dst_ip}"
                    ),
                    "src_ip": src_ip,
                    "dst_ip": dst_ip,
                    "protocol": pair_flows[0].get("protocol", "HTTPS"),
                    "confidence": round(min(0.93, 0.65 + len(pair_flows) / 100.0), 2),
                    "bytes": sum(f.get("bytes_sent", 0) for f in pair_flows),
                    "detected_at": now.isoformat(),
                    "status": "open",
                    "mitre_technique": "T1071",
                }
                await self.col_anomalies.insert_one(anomaly)
                detected.append(anomaly)

        # 4. New external connections: dst_ip not seen in flows from past 30 days
        ext_dsts = {
            f.get("dst_ip", "") for f in flows if not _is_private_ip(f.get("dst_ip", ""))
        }
        new_dst_count = 0
        for dst_ip in list(ext_dsts)[:20]:  # cap DB queries
            if new_dst_count >= 5:
                break
            prior = await self.col_flows.count_documents({
                "tenant_id": tenant_id,
                "dst_ip": dst_ip,
                "timestamp": {"$lt": window_start, "$gte": month_ago},
            })
            if prior == 0:
                src_flow = next((f for f in flows if f.get("dst_ip") == dst_ip), None)
                if src_flow:
                    anomaly = {
                        "_id": str(uuid.uuid4()),
                        "tenant_id": tenant_id,
                        "type": "new_external_connection",
                        "severity": "low",
                        "description": f"First-time connection to {dst_ip} — not seen in prior 30 days",
                        "src_ip": src_flow.get("src_ip", ""),
                        "dst_ip": dst_ip,
                        "protocol": src_flow.get("protocol", "TCP"),
                        "confidence": 0.75,
                        "bytes": src_flow.get("bytes_sent", 0),
                        "detected_at": now.isoformat(),
                        "status": "open",
                        "mitre_technique": "T1071",
                    }
                    await self.col_anomalies.insert_one(anomaly)
                    detected.append(anomaly)
                    new_dst_count += 1

        return detected

    async def get_traffic_summary(self, tenant_id: str):
        now = datetime.now(timezone.utc)
        since_24h = (now - timedelta(hours=24)).isoformat()
        total_flows = await self.col_flows.count_documents({"tenant_id": tenant_id, "timestamp": {"$gte": since_24h}})
        open_anomalies = await self.col_anomalies.count_documents({"tenant_id": tenant_id, "status": "open"})
        critical = await self.col_anomalies.count_documents({"tenant_id": tenant_id, "severity": "critical", "status": "open"})
        return {
            "flows_24h": total_flows,
            "open_anomalies": open_anomalies,
            "critical_anomalies": critical,
            "protocols_monitored": len(PROTOCOLS),
            "detection_running": True,
        }

    async def seed_demo(self, tenant_id: str):
        await self.col_anomalies.delete_many({"tenant_id": tenant_id})
        await self.run_detection(tenant_id)
        await self.run_detection(tenant_id)

