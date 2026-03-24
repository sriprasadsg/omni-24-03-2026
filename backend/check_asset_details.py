"""
Check what data is stored for the EILT0197 asset
"""
import asyncio
import sys
sys.path.insert(0, '.')

from database import connect_to_mongo, get_database, close_mongo_connection
import json

async def check_asset():
    await connect_to_mongo()
    db = get_database()
    
    # Get the asset
    asset = await db.assets.find_one({"id": "agent-EILT0197"})
    
    if asset:
        print("✅ Asset found!")
        print("\n📋 Asset Data:")
        print(json.dumps(asset, indent=2, default=str))
    else:
        print("❌ Asset not found!")
    
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(check_asset())
