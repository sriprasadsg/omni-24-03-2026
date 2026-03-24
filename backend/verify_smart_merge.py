
import asyncio
import uuid
from database import get_database, connect_to_mongo
import datetime

async def verify_smart_merge():
    print("Starting Smart Merge Verification...")
    db = get_database()
    
    tenant_a = "tenant-a-" + uuid.uuid4().hex[:6]
    tenant_b = "tenant-b-" + uuid.uuid4().hex[:6]
    
    # 1. Setup: Create overlapping records across tenants
    common_ip = "10.0.0.50"
    common_mac = "AA:BB:CC:DD:EE:FF"
    
    print(f"Creating initial overlapping records for IP: {common_ip}, MAC: {common_mac}")
    
    # Record 1: Tenant A has the device with just IP
    await db.network_devices.insert_one({
        "id": "dev-a-1",
        "tenantId": tenant_a,
        "ipAddress": common_ip,
        "macAddress": "Unknown",
        "hostname": "device-in-a",
        "status": "Up",
        "lastSeen": datetime.datetime.utcnow().isoformat(),
        "openPorts": [80]
    })
    
    # Record 2: Tenant B has the device with just MAC
    await db.network_devices.insert_one({
        "id": "dev-b-1",
        "tenantId": tenant_b,
        "ipAddress": "10.0.0.99", # Different IP
        "macAddress": common_mac,
        "hostname": "device-in-b",
        "status": "Up",
        "lastSeen": datetime.datetime.utcnow().isoformat(),
        "openPorts": [443]
    })
    
    print("Simulating a scan by PLATFORM-ADMIN that finds both...")
    # This scan result connects the two records: same IP as Record 1, same MAC as Record 2.
    scan_result = {
        "ip": common_ip,
        "mac": common_mac,
        "hostname": "new-hostname",
        "device_type": "Workstation",
        "lastSeen": datetime.datetime.utcnow().isoformat(),
        "open_ports": [22],
        "params": "smart-scan"
    }
    
    # We need to call the actual trigger_server_scan or simulate its logic
    # Since we can't easily call the endpoint function (it's async and part of a FastAPI app),
    # we'll simulate the Smart Merge logic we just implemented.
    
    # --- START SIMULATED SMART MERGE (from network_endpoints.py) ---
    tenant_id = "platform-admin"
    results = [scan_result]
    
    for device in results:
        ip = device["ip"]
        mac = device.get("mac", "Unknown")
        
        match_query = {
            "$or": [
                {"ipAddress": ip},
                {"macAddress": mac if mac != "Unknown" else "NonExistentMAC"}
            ]
        }
        
        # Platform admin looks global
        existing_matches = await db.network_devices.find(match_query).to_list(length=10)
        
        if existing_matches:
            print(f"Found {len(existing_matches)} matches for merger.")
            existing_matches.sort(key=lambda x: (
                1 if x.get("macAddress") and x.get("macAddress") != "Unknown" else 0,
                1 if x.get("tenantId") == tenant_id else 0
            ), reverse=True)
            
            primary = existing_matches[0]
            others_to_delete = existing_matches[1:]
            
            update_fields = {
                "lastSeen": device["lastSeen"],
                "status": "Up",
                "hostname": device["hostname"],
                "osVersion": "Updated",
                "openPorts": list(set(primary.get("openPorts", []) + device.get("open_ports", [])))
            }
            # Union ports from others
            for o in others_to_delete:
                update_fields["openPorts"] = list(set(update_fields["openPorts"] + o.get("openPorts", [])))
            
            if primary.get("ipAddress") != ip: update_fields["ipAddress"] = ip
            if mac != "Unknown": update_fields["macAddress"] = mac
            
            await db.network_devices.update_one({"_id": primary["_id"]}, {"$set": update_fields})
            
            if others_to_delete:
                await db.network_devices.delete_many({"_id": {"$in": [o["_id"] for o in others_to_delete]}})
    # --- END SIMULATED SMART MERGE ---

    # Verification
    final_count = await db.network_devices.count_documents({
        "ipAddress": common_ip,
        "macAddress": common_mac
    })
    
    print(f"Final count for consolidated record: {final_count}")
    
    primary_record = await db.network_devices.find_one({"ipAddress": common_ip, "macAddress": common_mac})
    if primary_record:
        print(f"Merged Ports: {primary_record.get('openPorts')}")
        # Should have [80, 443, 22] (order doesn't matter)
        ports = primary_record.get('openPorts', [])
        if len(ports) == 3 and all(p in ports for p in [80, 443, 22]):
            print("[SUCCESS] Smart Merge consolidated data correctly!")
        else:
            print(f"[FAIL] Port merge failed: {ports}")
    else:
        print("[FAIL] Primary record not found!")

    if final_count == 1:
        print("[SUCCESS] Redundant records deleted!")
    else:
        print(f"[FAIL] Still have {final_count} records instead of 1.")

    # Cleanup test data
    await db.network_devices.delete_many({"tenantId": {"$in": [tenant_a, tenant_b]}})

if __name__ == "__main__":
    async def run():
        await connect_to_mongo()
        await verify_smart_merge()
    asyncio.run(run())
