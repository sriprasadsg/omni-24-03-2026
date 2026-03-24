
from database import get_database, connect_to_mongo
from auth_utils import hash_password
import asyncio

async def create_user():
    await connect_to_mongo()
    db = get_database()
    
    email = "super@omni.ai"
    password = "superpassword"
    hashed = hash_password(password)
    
    user = {
        "id": "u-super-admin",
        "email": email,
        "password": hashed,
        "name": "Super Admin",
        "role": "Super Admin",
        "tenantId": "platform-admin",
        "status": "Active",
        "avatar": "https://github.com/shadcn.png"
    }
    
    # Upsert
    await db.users.update_one({"email": email}, {"$set": user}, upsert=True)
    print(f"User {email} created/updated.")

if __name__ == "__main__":
    asyncio.run(create_user())
