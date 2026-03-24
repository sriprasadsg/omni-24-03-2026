
import asyncio
import random
import logging
from datetime import datetime, timezone
from websocket_manager import broadcast_network_traffic
from database import get_database

logger = logging.getLogger(__name__)

async def run_network_traffic_simulator():
    """
    Simulates realistic enterprise network traffic patterns for all active tenants.
    Internet -> Perimeter -> LAN and LAN <-> LAN traffic.
    """
    logger.info("Starting Enterprise Network Traffic Simulator (Multi-Tenant)...")
    
    PROTOCOLS = [
        {"name": "HTTPS", "port": 443, "weight": 60},
        {"name": "DNS", "port": 53, "weight": 15},
        {"name": "SSH", "port": 22, "weight": 10},
        {"name": "DB", "port": 5432, "weight": 5},
        {"name": "Other", "port": 0, "weight": 10}
    ]
    
    while True:
        try:
            db = get_database()
            if not db:
                await asyncio.sleep(5)
                continue

            # Fetch all tenants
            tenants = await db.tenants.find({}, {"_id": 0, "id": 1}).to_list(length=100)
            tenant_ids = [t["id"] for t in tenants]
            if "default" not in tenant_ids:
                tenant_ids.append("default")

            for tenant_id in tenant_ids:
                # Fetch devices to know where to send traffic
                devices = await db.network_devices.find({"tenantId": tenant_id}).to_list(length=100)
                if not devices:
                    continue
                
                # 1. External Traffic: Internet -> Real Device
                target = random.choice(devices)
                target_ip = target.get("ipAddress") or target.get("ip")
                
                if target_ip:
                    status = "blocked" if random.random() < 0.25 else "allowed"
                    proto = random.choices(
                        [p["name"] for p in PROTOCOLS], 
                        weights=[p["weight"] for p in PROTOCOLS]
                    )[0]
                    
                    await broadcast_network_traffic(tenant_id, {
                        "source": "8.8.8.8", # Internet Node Dummy IP
                        "target": target_ip,
                        "protocol": proto,
                        "status": status
                    })
                
                # 2. Internal Traffic: LAN -> LAN
                if len(devices) > 1:
                    pair = random.sample(devices, 2)
                    src_ip = pair[0].get("ipAddress") or pair[0].get("ip")
                    dst_ip = pair[1].get("ipAddress") or pair[1].get("ip")
                    
                    if src_ip and dst_ip:
                        await broadcast_network_traffic(tenant_id, {
                            "source": src_ip,
                            "target": dst_ip,
                            "protocol": random.choice(["DB", "HTTPS", "SSH"]),
                            "status": "allowed"
                        })
            
            # Natural rhythm
            await asyncio.sleep(random.uniform(0.3, 1.2))
            
        except Exception as e:
            logger.error(f"Simulator Multi-Tenant Error: {e}")
            await asyncio.sleep(5)
