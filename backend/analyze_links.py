
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def analyze_links():
    client = AsyncIOMotorClient("mongodb://127.0.0.1:27017")
    db = client.omni_platform
    
    agents_with_asset = await db.agents.count_documents({"assetId": {"$exists": True, "$ne": None}})
    agents_without_asset = await db.agents.count_documents({"assetId": {"$exists": False}})
    
    unique_asset_ids = await db.agents.distinct("assetId")
    
    print(f"Agent-Asset Link Analysis:")
    print(f"--------------------------")
    print(f"Agents with assetId: {agents_with_asset}")
    print(f"Agents WITHOUT assetId: {agents_without_asset}")
    print(f"Unique assetIds referenced by agents: {len(unique_asset_ids)}")
    print(f"First 10 unique assetIds: {unique_asset_ids[:10]}")
    
    # Check if these referenced assets actually exist in the assets collection
    existing_assets_count = await db.assets.count_documents({"id": {"$in": unique_asset_ids}})
    print(f"Referenced assets that actually exist in 'assets' collection: {existing_assets_count}")

if __name__ == "__main__":
    asyncio.run(analyze_links())
