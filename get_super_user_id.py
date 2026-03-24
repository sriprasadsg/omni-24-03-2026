
import asyncio
import os
import sys
from motor.motor_asyncio import AsyncIOMotorClient

async def get_user_id():
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client['omni_platform']
    user = await db.users.find_one({'email': 'super@omni.ai'})
    if user:
        print(f"USER_ID: {user.get('id')}")
        print(f"TENANT_ID: {user.get('tenantId')}")
    else:
        print("User super@omni.ai not found")
    client.close()

if __name__ == "__main__":
    asyncio.run(get_user_id())
