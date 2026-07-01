import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def seed_active_agent():
    print("--- SEEDING ACTIVE AGENT ---")
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["omni_platform"]
    
    agent_id = "agent-local-audit"
    hostname = "EILT0197"
    
    agent = {
        "id": agent_id,
        "name": "Local Diagnostic Agent",
        "hostname": hostname,
        "status": "Online",
        "lastSeen": "2026-02-26T18:00:00Z",
        "platform": "windows",
        "osName": "Windows 11",
        "ipAddress": "127.0.0.1",
        "tenantId": "default"
    }
    
    await db.agents.update_one(
        {"id": agent_id},
        {"$set": agent},
        upsert=True
    )
    print(f"✅ Mock Agent {agent_id} ({hostname}) is now Online.")
    client.close()

if __name__ == "__main__":
    asyncio.run(seed_active_agent())
