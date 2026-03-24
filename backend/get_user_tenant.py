from database import connect_to_mongo, close_mongo_connection, get_database
import asyncio

async def main():
    await connect_to_mongo()
    db = get_database()
    user = await db.users.find_one({"email": "testadmin@example.com"})
    if user:
        print(f"TenantID: {user.get('tenantId')}")
    else:
        print("User not found")
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(main())
