
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv
import bcrypt

load_dotenv()

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

async def manual_seed():
    mongo_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    # THE CORRECT DB NAME IS omni_platform
    db_name = os.getenv("MONGODB_DB_NAME", "omni_platform")
    
    print(f"Connecting to {mongo_url}, database: {db_name}...")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    user_data = {
        "id": "user-super-admin-001",
        "tenantId": "platform-admin",
        "tenantName": "Platform",
        "name": "Super Admin",
        "email": "super@omni.ai",
        "password": hash_password("password123"),
        "role": "Super Admin",
        "status": "Active",
    }
    
    # Check if user exists
    existing = await db.users.find_one({"email": "super@omni.ai"})
    if existing:
        print("Updating existing super admin...")
        await db.users.update_one({"email": "super@omni.ai"}, {"$set": user_data})
    else:
        print("Inserting new super admin...")
        await db.users.insert_one(user_data)
        
    print(f"Super Admin seeded successfully in {db_name}: super@omni.ai / password123")
    
if __name__ == "__main__":
    asyncio.run(manual_seed())
