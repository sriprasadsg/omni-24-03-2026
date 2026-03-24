import asyncio
from database import connect_to_mongo, close_mongo_connection, get_database

async def check_users():
    await connect_to_mongo()
    db = get_database()
    users = await db.users.find({}, {"_id": 0}).to_list(length=None)
    print("ALL USERS:")
    for u in users:
        print(f"  - {u.get('email')} (Tenant: {u.get('tenantId')}, Role: {u.get('role')})")
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(check_users())
