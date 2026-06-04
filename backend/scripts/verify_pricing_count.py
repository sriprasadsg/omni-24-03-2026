"""
Quick verification of service pricing count and categories
"""
import asyncio
from database import connect_to_mongo, get_database, close_mongo_connection

async def verify_services():
    try:
        await connect_to_mongo()
        db = get_database()
        
        if not db:
            print("Failed to connect")
            return
        
        # Get total count
        total = await db.service_pricing.count_documents({})
        print(f"Total Services: {total}")
        
        #Get by category
        categories = await db.service_pricing.aggregate([
            {"$group": {"_id": "$category", "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}}
        ]).to_list(length=100)
        
        print("\nBy Category:")
        for cat in categories:
            print(f"  {cat['_id']}: {cat['count']}")
        
        await close_mongo_connection()
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(verify_services())
