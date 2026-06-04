
import asyncio
from database import get_database

async def check_duplicates():
    db = get_database()
    print("Checking for duplicate network devices (IP or MAC within a tenant)...")
    
    # Get all devices
    devices = await db.network_devices.find({}).to_list(1000)
    
    tenants = set(d.get("tenantId") for d in devices)
    print(f"Unique tenants in DB: {tenants}")
    
    # Group by (tenantId, ipAddress)
    ip_groups = {}
    for d in devices:
        key = (d.get("tenantId"), d.get("ipAddress"))
        if key not in ip_groups:
            ip_groups[key] = []
        ip_groups[key].append(d)
    
    # Group by (tenantId, macAddress)
    mac_groups = {}
    for d in devices:
        mac = d.get("macAddress")
        if mac and mac != "Unknown":
            key = (d.get("tenantId"), mac)
            if key not in mac_groups:
                mac_groups[key] = []
            mac_groups[key].append(d)

    # Group by hostname (within tenant)
    hostname_groups = {}
    for d in devices:
        host = d.get("hostname")
        if host and host != d.get("ipAddress"): # Ignore if hostname is just the IP
            key = (d.get("tenantId"), host)
            if key not in hostname_groups:
                hostname_groups[key] = []
            hostname_groups[key].append(d)
            
    print(f"Total devices checked: {len(devices)}")
    
    # Group by ipAddress (ignore tenant)
    ip_groups_global = {}
    for d in devices:
        ip = d.get("ipAddress")
        if not ip: continue
        if ip not in ip_groups_global:
            ip_groups_global[ip] = []
        ip_groups_global[ip].append(d)
    
    # Group by macAddress (ignore tenant)
    mac_groups_global = {}
    for d in devices:
        mac = d.get("macAddress")
        if mac and mac != "Unknown":
            if mac not in mac_groups_global:
                mac_groups_global[mac] = []
            mac_groups_global[mac].append(d)
            
    print("\nGlobal Duplicate IPs found (across tenants):")
    found_global_ip = False
    for ip, devs in ip_groups_global.items():
        if len(devs) > 1:
            found_global_ip = True
            print(f"IP: {ip}, Count: {len(devs)}")
            for d in devs:
                print(f"  - Tenant: {d.get('tenantId')}, ID: {d.get('id')}, MAC: {d.get('macAddress')}")
    if not found_global_ip:
        print("None")

    print("\nGlobal Duplicate MACs found (across tenants):")
    found_global_mac = False
    for mac, devs in mac_groups_global.items():
        if len(devs) > 1:
            found_global_mac = True
            print(f"MAC: {mac}, Count: {len(devs)}")
            for d in devs:
                print(f"  - Tenant: {d.get('tenantId')}, ID: {d.get('id')}, IP: {d.get('ipAddress')}")
    if not found_global_mac:
        print("None")

    print("\nDuplicate Hostnames found (within tenant):")
    found_host_dupes = False
    for key, devs in hostname_groups.items():
        if len(devs) > 1:
            found_host_dupes = True
            print(f"Tenant: {key[0]}, Hostname: {key[1]}, Count: {len(devs)}")
            for d in devs:
                print(f"  - ID: {d.get('id')}, IP: {d.get('ipAddress')}, MAC: {d.get('macAddress')}")
    if not found_host_dupes:
        print("None")

if __name__ == "__main__":
    from database import connect_to_mongo
    async def run():
        await connect_to_mongo()
        await check_duplicates()
    asyncio.run(run())
