import asyncio
import random
import logging
from datetime import datetime, timezone, timedelta
from websocket_manager import broadcast_network_traffic
from database import get_database

logger = logging.getLogger(__name__)

PROTOCOLS = [
    {"name": "HTTPS", "port": 443, "weight": 60},
    {"name": "DNS",   "port": 53,  "weight": 15},
    {"name": "SSH",   "port": 22,  "weight": 10},
    {"name": "DB",    "port": 5432,"weight": 5},
    {"name": "Other", "port": 0,   "weight": 10},
]
PROTOCOL_NAMES = [p["name"] for p in PROTOCOLS]
PROTOCOL_WEIGHTS = [p["weight"] for p in PROTOCOLS]


async def run_network_traffic_simulator():
    """
    Broadcasts real-time network traffic for all active tenants.

    Priority:
    1. Streams recent flows from the `network_flows` collection (last 5 min),
       which the NDR service populates from real agent telemetry.
    2. Falls back to device-pair simulation when no real flows are present,
       using actual device IPs from `network_devices`.
    """
    logger.info("Starting Network Traffic Broadcaster (Multi-Tenant)...")

    while True:
        try:
            db = get_database()
            if not db:
                await asyncio.sleep(5)
                continue

            tenants = await db.tenants.find({}, {"_id": 0, "id": 1}).to_list(length=100)
            tenant_ids = [t["id"] for t in tenants]
            if "default" not in tenant_ids:
                tenant_ids.append("default")

            for tenant_id in tenant_ids:
                # ── Try real flows first ──────────────────────────────────────
                cutoff = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
                real_flows = await db.network_flows.find(
                    {"tenantId": tenant_id, "timestamp": {"$gte": cutoff}},
                    {"_id": 0, "src_ip": 1, "dst_ip": 1, "protocol": 1, "action": 1}
                ).sort("timestamp", -1).limit(20).to_list(length=20)

                if real_flows:
                    for flow in real_flows:
                        src = flow.get("src_ip") or flow.get("source_ip", "")
                        dst = flow.get("dst_ip") or flow.get("dest_ip", "")
                        proto = flow.get("protocol", "HTTPS")
                        action = flow.get("action", "allow")
                        status = "blocked" if action in ("block", "deny", "blocked") else "allowed"
                        if src and dst:
                            await broadcast_network_traffic(tenant_id, {
                                "source": src, "target": dst,
                                "protocol": proto, "status": status
                            })
                    continue

                # ── Fallback: device-pair simulation ─────────────────────────
                devices = await db.network_devices.find(
                    {"tenantId": tenant_id}, {"_id": 0, "ipAddress": 1, "ip": 1}
                ).to_list(length=100)
                if not devices:
                    continue

                # External → internal
                target = random.choice(devices)
                target_ip = target.get("ipAddress") or target.get("ip")
                if target_ip:
                    proto = random.choices(PROTOCOL_NAMES, weights=PROTOCOL_WEIGHTS)[0]
                    status = "blocked" if random.random() < 0.15 else "allowed"
                    await broadcast_network_traffic(tenant_id, {
                        "source": "203.0.113.1",  # RFC 5737 documentation range
                        "target": target_ip,
                        "protocol": proto,
                        "status": status,
                    })

                # Internal → internal
                if len(devices) > 1:
                    pair = random.sample(devices, 2)
                    src_ip = pair[0].get("ipAddress") or pair[0].get("ip")
                    dst_ip = pair[1].get("ipAddress") or pair[1].get("ip")
                    if src_ip and dst_ip:
                        await broadcast_network_traffic(tenant_id, {
                            "source": src_ip,
                            "target": dst_ip,
                            "protocol": random.choice(["DB", "HTTPS", "SSH"]),
                            "status": "allowed",
                        })

            await asyncio.sleep(random.uniform(0.5, 1.5))

        except Exception as e:
            logger.error(f"Network traffic broadcaster error: {e}")
            await asyncio.sleep(5)
