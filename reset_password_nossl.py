
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
# import certifi
from backend.auth_utils import hash_password

MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "omni_platform"

async def reset_password():
    # REMOVED tlsCAFile
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
    
    email = "admin@exafluence.com"
    new_password = "password123"
    hashed = hash_password(new_password)
    
    print(f"Attempting to reset password for {email}...")
    result = await db.users.update_one(
        {"email": email},
        {"$set": {"password": hashed, "hashed_password": hashed}}
    )
    
    if result.modified_count > 0:
        print(f"SUCCESS: Password for {email} reset to {new_password}")
    else:
        print(f"WARNING: User {email} found but password not modified (maybe already same?) or User not found.")
        # Check if user exists
        user = await db.users.find_one({"email": email})
        if user:
            print("User exists.")
        else:
            print("User does NOT exist.")

if __name__ == "__main__":
    asyncio.run(reset_password())
