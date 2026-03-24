
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def count_assets():
    client = AsyncIOMotorClient("mongodb://127.0.0.1:27017")
    db = client.omni_platform
    
    total_assets = await db.assets.count_documents({})
    total_agents = await db.agents.count_documents({})
    
    print(f"Database Scan Results:")
    print(f"----------------------")
    print(f"Total Assets in DB: {total_assets}")
    print(f"Total Agents in DB: {total_agents}")
    
    # Check a few assets
    async for asset in db.assets.find().limit(5):
        print(f"Asset: {asset.get('hostname')} (ID: {asset.get('id')}) - Tenant: {asset.get('tenantId')}")

if __name__ == "__main__":
    asyncio.run(count_assets())
