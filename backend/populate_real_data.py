import asyncio
import json
import os
from database import connect_to_mongo, close_mongo_connection, get_database
import uuid
from datetime import datetime

async def main():
    if not os.path.exists("scan_results.json"):
        print("Error: scan_results.json not found. Run run_real_scan.py first.")
        return

    with open("scan_results.json", "r", encoding="utf-8") as f:
        results = json.load(f)

    print(f"Loaded {len(results)} scanned devices.")
    
    await connect_to_mongo()
    db = get_database()
    
    # Get all tenants
    tenants = await db.tenants.find({}, {"_id": 0, "id": 1}).to_list(length=100)
    tenant_ids = [t["id"] for t in tenants]
    if "default" not in tenant_ids:
        tenant_ids.append("default")
        
    print(f"Found {len(tenant_ids)} tenants to populate.")
    
    for tenant_id in tenant_ids:
        print(f"Processing tenant: {tenant_id}")
        for device in results:
            # Check if device already exists
            existing = await db.network_devices.find_one({
                "tenantId": tenant_id,
                "ipAddress": device["ip"]
            })
            
            if existing:
                await db.network_devices.update_one(
                    {"_id": existing["_id"]},
                    {"$set": {
                        "lastSeen": datetime.utcnow().isoformat(),
                        "status": "Up",
                        "hostname": device["hostname"],
                        "macAddress": device.get("mac", "Unknown"),
                        "vendor": device.get("vendor", "Unknown"),
                        "osVersion": device.get("os_version", "Unknown"),
                        "openPorts": device.get("open_ports", []),
                        "deviceType": device.get("device_type", "Unknown")
                    }}
                )
            else:
                new_dev = {
                    "id": f"net-dev-{uuid.uuid4().hex[:12]}",
                    "tenantId": tenant_id,
                    "hostname": device["hostname"],
                    "ipAddress": device["ip"],
                    "macAddress": device.get("mac"),
                    "deviceType": device.get("device_type", "Unknown"),
                    "status": "Up",
                    "lastSeen": datetime.utcnow().isoformat(),
                    "vendor": device.get("vendor", "Unknown"),
                    "osVersion": device.get("os_version", "Unknown"),
                    "openPorts": device.get("open_ports", []),
                    "subnet": device.get("subnet", "Unknown"),
                    "interfaces": [],
                    "configBackups": [],
                    "vulnerabilities": []
                }
                await db.network_devices.insert_one(new_dev)
    
    print("Population complete.")
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(main())
