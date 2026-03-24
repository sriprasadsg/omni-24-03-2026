
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os

async def check_users():
    mongodb_uri = "mongodb://localhost:27017"
    client = AsyncIOMotorClient(mongodb_uri)
    db = client.omni_platform
    
    users = await db.users.find({}).to_list(length=100)
    with open("users_output.txt", "w") as f:
        f.write(f"Total users found: {len(users)}\n")
        for u in users:
            f.write(f"ID: {u.get('_id')}, Email: {u.get('email')}, Tenant: {u.get('tenantId')}, Name: {u.get('full_name') or u.get('name')}\n")

if __name__ == "__main__":
    asyncio.run(check_users())
