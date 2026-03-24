import asyncio
from database import connect_to_mongo, close_mongo_connection, get_database

async def check_tenants():
    await connect_to_mongo()
    db = get_database()
    tenants = await db.tenants.find({}, {"_id": 0}).to_list(length=None)
    print("EXISTING TENANTS:")
    for t in tenants:
        print(f"  - {t.get('id')} ({t.get('name')})")
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(check_tenants())
