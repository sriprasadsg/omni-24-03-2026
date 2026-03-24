import asyncio
from backend.database import get_database, connect_to_mongo

async def check_user():
    await connect_to_mongo()
    db = get_database()
    user = await db.users.find_one({"email": "browser_test_user_v1@example.com"})
    if user:
        print(f"User FOUND: {user['email']}, Tenant: {user.get('tenantId')}")
    else:
        print("User NOT found.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(check_user())
