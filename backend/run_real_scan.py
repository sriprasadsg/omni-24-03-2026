import asyncio
import json
from server_discovery import ServerDiscovery
from database import connect_to_mongo, close_mongo_connection, get_database
import uuid
from datetime import datetime

async def main():
    print("Starting network discovery scan...")
    # Get all local subnets
    subnets = ServerDiscovery._get_all_local_subnets()
    print(f"Detected subnets: {subnets}")
    
    # Run scan
    results = ServerDiscovery.start_scan(scan_all_networks=True)
    print(f"Scan complete. Found {len(results)} devices.")
    
    # Optionally: Update DB with these devices so they show up in the topology
    await connect_to_mongo()
    db = get_database()
    tenant_id = "tenant_test_123" # Use a test tenant or the one from current user
    
    print(f"Upserting {len(results)} devices into db.network_devices for tenant {tenant_id}...")
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
                    "openPorts": device.get("open_ports", [])
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
                "subnet": device.get("subnet", "Unknown")
            }
            await db.network_devices.insert_one(new_dev)
    
    await close_mongo_connection()
    
    # Output to JSON for verification
    with open("scan_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("Results saved to scan_results.json")

if __name__ == "__main__":
    asyncio.run(main())
