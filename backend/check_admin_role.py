from database import get_database, connect_to_mongo
import asyncio

async def check_user_role():
    try:
        await connect_to_mongo()
        db = get_database()
        user = await db.users.find_one({"email": "testadmin@example.com"})
        if user:
            print(f"User: {user.get('email')}")
            print(f"Role: {user.get('role')}")
            print(f"Tenant: {user.get('tenantId')}")
        else:
            print("User testadmin@example.com NOT FOUND")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(check_user_role())
