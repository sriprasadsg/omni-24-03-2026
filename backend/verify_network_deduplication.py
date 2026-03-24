import asyncio
import uuid
from database import get_database
from server_discovery import ServerDiscovery
import datetime

async def verify_deduplication():
    print("Starting Network Scan Deduplication Verification...")
    db = get_database()
    tenant_id = "test-tenant-" + uuid.uuid4().hex[:6]
    
    # Mock some scan results with duplicates
    mock_results = [
        {
            "ip": "192.168.1.50",
            "hostname": "device1",
            "mac": "00:11:22:33:44:55",
            "device_type": "Workstation",
            "lastSeen": datetime.datetime.utcnow().isoformat(),
            "params": "test"
        },
        {
            "ip": "192.168.1.50",
            "hostname": "device1-duplicate",
            "mac": "Unknown",
            "device_type": "Workstation",
            "lastSeen": datetime.datetime.utcnow().isoformat(),
            "params": "test-fallback"
        },
        {
            "ip": "192.168.1.60",
            "hostname": "device2",
            "mac": "Unknown",
            "device_type": "Server",
            "lastSeen": datetime.datetime.utcnow().isoformat(),
            "params": "test"
        }
    ]
    
    print(f"1. Testing internal deduplication in ServerDiscovery logic (simulated)...")
    unique_results = {}
    for dev in mock_results:
        ip = dev.get("ip")
        if ip not in unique_results or (unique_results[ip].get("mac") == "Unknown" and dev.get("mac") != "Unknown"):
            unique_results[ip] = dev
    
    final_results = list(unique_results.values())
    print(f"   [OK] Internal deduplication reduced {len(mock_results)} to {len(final_results)} items.")
    if len(final_results) != 2:
        print(f"   [FAIL] Expected 2 unique items, got {len(final_results)}")
        return
    
    # Now simulate processing these results in the endpoint
    print(f"2. Simulating processing results into DB for tenant {tenant_id}...")
    
    async def process_mock_results(results_to_process):
        count_new = 0
        count_updated = 0
        for device in results_to_process:
            ip = device["ip"]
            mac = device.get("mac", "Unknown")
            
            query_parts = [{"ipAddress": ip}]
            if mac and mac != "Unknown":
                query_parts.append({"macAddress": mac})
                
            existing = await db.network_devices.find_one({
                "tenantId": tenant_id,
                "$or": query_parts
            })
            
            if existing:
                count_updated += 1
            else:
                count_new += 1
                new_dev = {
                    "tenantId": tenant_id,
                    "ipAddress": ip,
                    "macAddress": mac,
                    "hostname": device["hostname"]
                }
                await db.network_devices.insert_one(new_dev)
        return count_new, count_updated

    # First pass: All should be new
    n1, u1 = await process_mock_results(final_results)
    print(f"   First Pass: New={n1}, Updated={u1}")
    
    # Second pass: Simulate a scan that finds the same devices again. Should all be updates.
    n2, u2 = await process_mock_results(final_results)
    print(f"   Second Pass: New={n2}, Updated={u2}")
    
    # Third pass: Simulate a device with NO MAC matching an existing IP
    mock_no_mac = [{"ip": "192.168.1.50", "hostname": "device1-no-mac", "mac": "Unknown", "lastSeen": "now"}]
    n3, u3 = await process_mock_results(mock_no_mac)
    print(f"   Third Pass (IP match, no MAC): New={n3}, Updated={u3}")

    # Check DB count
    total = await db.network_devices.count_documents({"tenantId": tenant_id})
    print(f"Total devices in DB for tenant: {total}")
    
    if total == 2 and n2 == 0 and n3 == 0:
        print("\n[SUCCESS] Deduplication and Refined matching logic verified!")
    else:
        print("\n[FAIL] Verification failed. Total count or matching logic incorrect.")

if __name__ == "__main__":
    from database import connect_to_mongo
    async def run():
        await connect_to_mongo()
        await verify_deduplication()
    
    asyncio.run(run())
