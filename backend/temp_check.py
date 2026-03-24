import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient

async def check_db():
    client = AsyncIOMotorClient(os.getenv("MONGODB_URI", "mongodb://localhost:27017"))
    db = client.omni_platform
    
    tenants = await db.tenants.find().to_list(None)
    agents = await db.agents.find().to_list(None)
    assets = await db.assets.find().to_list(None)
    
    print("Tenants:")
    for t in tenants:
         print(f" - {t.get('name')} (ID: {t.get('id')}, Key: {t.get('registrationKey')})")
         
    print("\nAgents:")
    for a in agents:
         print(f" - {a.get('hostname')} (ID: {a.get('id')}, Tenant: {a.get('tenantId')}, Status: {a.get('status')})")

    print("\nAssets:")
    for a in assets:
         print(f" - {a.get('hostname')} (ID: {a.get('id')}, Tenant: {a.get('tenantId')})")

if __name__ == "__main__":
    asyncio.run(check_db())
