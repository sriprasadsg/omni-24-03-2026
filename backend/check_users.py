import asyncio
from database import connect_to_mongo, get_database

async def check():
    await connect_to_mongo()
    db = get_database()
    users = await db.users.find().to_list(100)
    print(f"Found {len(users)} users:")
    for u in users:
        print(f"- {u.get('email')} : {u.get('role')} (Tenant: {u.get('tenantId')})")
        # Do not print password hash, but check if password field exists
        print(f"  Has password: {'password' in u}")

if __name__ == "__main__":
    asyncio.run(check())
