import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from auth_utils import hash_password

async def reset_admin_password():
    MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    DB_NAME = os.getenv("MONGODB_DB_NAME", "omni_platform")
    
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DB_NAME]
    
    email = "admin@acmecorp.com"
    new_password = "password123"
    hashed = hash_password(new_password)
    
    result = await db.users.update_one(
        {"email": email},
        {"$set": {"password": hashed, "hashed_password": hashed}}
    )
    
    if result.modified_count > 0:
        print(f"✅ Password for {email} reset to 'password123'")
    else:
        # Check if user exists
        user = await db.users.find_one({"email": email})
        if user:
            print(f"ℹ Password for {email} was already set correctly or hash matched.")
        else:
            print(f"❌ User {email} not found.")
            
    client.close()

if __name__ == "__main__":
    reset_admin_password_func = reset_admin_password
    asyncio.run(reset_admin_password_func())
