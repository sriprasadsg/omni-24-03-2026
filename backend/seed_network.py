
import asyncio
from database import connect_to_mongo, get_database, close_mongo_connection
import uuid
from datetime import datetime

async def seed_network():
    print("Connecting to database...")
    await connect_to_mongo()
    db = get_database()

    print("Clearing existing network devices...")
    await db.network_devices.delete_many({})

    devices = []
    
    # Subnet 1: Core Infrastructure (192.168.1.0/24)
    devices.append({
        "id": f"net-dev-{uuid.uuid4().hex[:12]}",
        "hostname": "Core-Router-01",
        "ipAddress": "192.168.1.1",
        "macAddress": "00:11:22:33:44:01",
        "deviceType": "Router",
        "subnet": "192.168.1.0/24",
        "status": "Up",
        "lastSeen": datetime.utcnow().isoformat(),
        "tenantId": "default",
        "interfaces": [], "configBackups": [], "vulnerabilities": []
    })
    devices.append({
        "id": f"net-dev-{uuid.uuid4().hex[:12]}",
        "hostname": "Core-Firewall",
        "ipAddress": "192.168.1.254",
        "macAddress": "00:11:22:33:44:FE",
        "deviceType": "Firewall",
        "subnet": "192.168.1.0/24",
        "status": "Up",
        "lastSeen": datetime.utcnow().isoformat(),
        "tenantId": "default",
        "interfaces": [], "configBackups": [], "vulnerabilities": []
    })

    # Subnet 2: Server Farm (10.0.0.0/24)
    for i in range(1, 6):
        devices.append({
            "id": f"net-dev-{uuid.uuid4().hex[:12]}",
            "hostname": f"Web-Server-0{i}",
            "ipAddress": f"10.0.0.{10+i}",
            "macAddress": f"00:AA:BB:CC:00:0{i}",
            "deviceType": "Linux Web Server",
            "subnet": "10.0.0.0/24",
            "status": "Up",
            "lastSeen": datetime.utcnow().isoformat(),
            "tenantId": "default",
            "interfaces": [], "configBackups": [], "vulnerabilities": []
        })

    devices.append({
        "id": f"net-dev-{uuid.uuid4().hex[:12]}",
        "hostname": "DB-Primary",
        "ipAddress": "10.0.0.50",
        "macAddress": "00:AA:BB:CC:00:50",
        "deviceType": "Linux Database Server",
        "subnet": "10.0.0.0/24",
        "status": "Up",
        "lastSeen": datetime.utcnow().isoformat(),
        "tenantId": "default",
        "interfaces": [], "configBackups": [], "vulnerabilities": []
    })

    # Subnet 3: IoT / Office (172.16.0.0/16)
    for i in range(1, 4):
        devices.append({
            "id": f"net-dev-{uuid.uuid4().hex[:12]}",
            "hostname": f"Office-Printer-0{i}",
            "ipAddress": f"172.16.0.{100+i}",
            "macAddress": f"00:11:22:DD:EE:0{i}",
            "deviceType": "Printer",
            "subnet": "172.16.0.0/16",
            "status": "Up",
            "lastSeen": datetime.utcnow().isoformat(),
            "tenantId": "default",
            "interfaces": [], "configBackups": [], "vulnerabilities": []
        })

    print(f"Seeding {len(devices)} devices...")
    if devices:
        await db.network_devices.insert_many(devices)
    
    print("Done!")
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(seed_network())
