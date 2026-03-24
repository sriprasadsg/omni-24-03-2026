import asyncio
import uuid
from datetime import datetime, timezone
from database import connect_to_mongo, get_database

AGENTS_DATA = [
    {
        "id": "agent-1",
        "tenantId": "tenant_f15daa22a46a", # Acme
        "assetId": "asset-1",
        "hostname": "db-prod-01",
        "platform": "Linux",
        "status": "Online",
        "version": "2.1.0",
        "ipAddress": "10.0.1.10",
        "lastSeen": datetime.now(timezone.utc).isoformat(),
        "capabilities": ["metrics_collection", "log_collection", "fim", "predictive_health", "ebpf_tracing"],
        "health": {
            "overallStatus": "Healthy",
            "checks": [
                {"name": "Connectivity", "status": "Pass", "message": "Agent connected"},
                {"name": "Service Status", "status": "Pass", "message": "Service running"},
            ]
        }
    },
    {
        "id": "agent-2",
        "tenantId": "tenant_f15daa22a46a", # Acme
        "assetId": "asset-2",
        "hostname": "web-server-03",
        "platform": "Windows",
        "status": "Online",
        "version": "2.0.5",
        "ipAddress": "10.0.2.15",
        "lastSeen": datetime.now(timezone.utc).isoformat(),
        "capabilities": ["metrics_collection", "vulnerability_scanning", "log_collection", "runtime_security"],
        "health": {
            "overallStatus": "Healthy",
            "checks": [
                {"name": "Connectivity", "status": "Pass", "message": "Agent connected"},
                {"name": "Service Status", "status": "Pass", "message": "High latency"},
            ]
        }
    },
    {
        "id": "agent-3",
        "tenantId": "tenant_c1344db58834", # Exafluence
        "assetId": "asset-3",
        "hostname": "dev-box-01",
        "platform": "Linux",
        "status": "Online",
        "version": "2.1.0",
        "ipAddress": "192.168.1.50",
        "lastSeen": datetime.now(timezone.utc).isoformat(),
        "capabilities": ["metrics_collection", "vulnerability_scanning"],
        "health": {
            "overallStatus": "Healthy",
            "checks": []
        }
    },
    {
        "id": "agent-4",
        "tenantId": "tenant_21b8ca5ffae0", # TestCorp123
        "assetId": "asset-4",
        "hostname": "test-host-01",
        "platform": "Windows",
        "status": "Online",
        "version": "2.1.0",
        "ipAddress": "192.168.20.5",
        "lastSeen": datetime.now(timezone.utc).isoformat(),
        "capabilities": ["metrics_collection", "log_collection"],
        "health": {
            "overallStatus": "Healthy",
            "checks": [
                {"name": "Connectivity", "status": "Pass", "message": "Agent connected"}
            ]
        }
    },
    {
        "id": "agent-5",
        "tenantId": "tenant_9d233e77f0a4", # Initech
        "assetId": "asset-5",
        "hostname": "ini-host-01",
        "platform": "Linux",
        "status": "Online",
        "version": "2.1.0",
        "ipAddress": "192.168.30.5",
        "lastSeen": datetime.now(timezone.utc).isoformat(),
        "capabilities": ["metrics_collection", "vulnerability_scanning"],
        "health": {
            "overallStatus": "Healthy",
            "checks": []
        }
    }
]

async def seed_agents():
    print("Connecting to MongoDB...")
    await connect_to_mongo()
    db = get_database()
    
    print("Clearing existing agents...")
    # Only delete seeded agents or all? Let's delete all for a clean slate.
    await db.agents.delete_many({})
    
    print(f"Seeding {len(AGENTS_DATA)} agents...")
    await db.agents.insert_many(AGENTS_DATA)
    
    print("Done!")

if __name__ == "__main__":
    asyncio.run(seed_agents())
