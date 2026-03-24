import sys
import os
import asyncio
sys.path.append(os.path.abspath("backend"))

from backend.database import connect_to_mongo, get_database

async def list_users():
    await connect_to_mongo()
    db = get_database()
    
    users = await db.users.find().to_list(length=10)
    for u in users:
        print(f"User: {u.get('email')} | Role: {u.get('role')} | Tenant: {u.get('tenantId')}")

if __name__ == "__main__":
    asyncio.run(list_users())
