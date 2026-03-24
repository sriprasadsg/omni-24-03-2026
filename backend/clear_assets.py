"""
Clear all assets from database
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def clear_all_assets():
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017')
    db = client['omni_platform']
    
    print("=" * 60)
    print("CLEARING ALL ASSETS FROM DATABASE")
    print("=" * 60)
    
    # Count before
    count_before = await db.assets.count_documents({})
    print(f"\nAssets before deletion: {count_before}")
    
    # Delete all
    result = await db.assets.delete_many({})
    print(f"Deleted: {result.deleted_count} assets")
    
    # Verify
    count_after = await db.assets.count_documents({})
    print(f"Assets after deletion: {count_after}")
    
    if count_after == 0:
        print("\n✅ All assets cleared successfully!")
    else:
        print(f"\n⚠️ Warning: {count_after} assets remain")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(clear_all_assets())
