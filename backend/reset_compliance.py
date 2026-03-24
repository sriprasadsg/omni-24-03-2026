import asyncio
import sys
import os

sys.path.append(os.path.join(os.getcwd(), 'backend'))
from database import connect_to_mongo, get_database, close_mongo_connection

async def reset_compliance():
    await connect_to_mongo()
    db = get_database()
    
    print("🧹 Wiping corrupted asset_compliance records...")
    result = await db.asset_compliance.delete_many({})
    print(f"✅ Deleted {result.deleted_count} historical records.")
    
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(reset_compliance())
