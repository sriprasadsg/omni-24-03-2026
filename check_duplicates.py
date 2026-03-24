
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import sys

# Connect to MongoDB
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "tenant_db"

async def check_duplicates():
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
    
    print(f"Checking {DB_NAME}.agents for duplicates...")
    
    pipeline = [
        {"$group": {"_id": "$id", "count": {"$sum": 1}, "docs": {"$push": "$_id"}}},
        {"$match": {"count": {"$gt": 1}}}
    ]
    
    cursor = db.agents.aggregate(pipeline)
    duplicates = await cursor.to_list(length=100)
    
    if not duplicates:
        print("✅ No duplicate Agent IDs found.")
    else:
        print(f"❌ Found {len(duplicates)} duplicate Agent IDs:")
        for dup in duplicates:
            print(f"  - ID: {dup['_id']} (Count: {dup['count']})")
            
    # Also check Assets just in case
    print(f"\nChecking {DB_NAME}.assets for duplicates...")
    cursor = db.assets.aggregate(pipeline)
    asset_dupes = await cursor.to_list(length=100)
    
    if not asset_dupes:
        print("✅ No duplicate Asset IDs found.")
    else:
        print(f"❌ Found {len(asset_dupes)} duplicate Asset IDs:")
        for dup in asset_dupes:
            print(f"  - ID: {dup['_id']} (Count: {dup['count']})")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(check_duplicates())
