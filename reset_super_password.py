import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from backend.auth_utils import hash_password
import logging

logging.basicConfig(level=logging.INFO)

MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "omni_platform"

async def reset_super_password():
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
    
    email = "super@omni.ai"
    new_password = "superadmin"
    hashed = hash_password(new_password)
    
    # Check if user exists
    user = await db.users.find_one({"email": email})
    
    if user:
        result = await db.users.update_one(
            {"email": email},
            {"$set": {
                "password": hashed, 
                "hashed_password": hashed,
                "role": "superadmin",
                "is_active": True,
                "is_superuser": True
            }}
        )
        if result.modified_count > 0:
            logging.info(f"✅ SUCCESS: Password for {email} reset to '{new_password}'")
        else:
            logging.info(f"ℹ️  User {email} found but no changes needed.")
    else:
        logging.info(f"⚠️  User {email} not found. Creating new superadmin user...")
        new_user = {
            "email": email,
            "username": "Super Admin",
            "password": hashed,
            "hashed_password": hashed,
            "role": "superadmin",
            "is_active": True,
            "is_superuser": True
        }
        await db.users.insert_one(new_user)
        logging.info(f"✅ SUCCESS: Created new superadmin user {email} with password '{new_password}'")

if __name__ == "__main__":
    asyncio.run(reset_super_password())
