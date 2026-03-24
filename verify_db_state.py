
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os

async def main():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["omni_platform"]
    
    print("--- DB Verification ---")
    agents = await db.agents.find({}).to_list(None)
    print(f"Total Agents in DB: {len(agents)}")
    for a in agents:
        print(f"Agent: {a.get('hostname')} | ID: {a.get('id')} | Tenant: {a.get('tenantId')}")

    tenants = await db.tenants.find({}).to_list(None)
    print(f"Total Tenants: {len(tenants)}")
    for t in tenants:
        print(f"Tenant: {t.get('name')} | ID: {t.get('id')}")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
