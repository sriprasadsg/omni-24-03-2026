import asyncio
import os
import sys
sys.path.append(os.path.join(os.getcwd(), "backend"))
from backend.database import get_database, connect_to_mongo
from backend.auth_utils import hash_password
from datetime import datetime, timezone
import uuid

async def seed():
    await connect_to_mongo()
    db = get_database()
    
    super_admin_data = {
        "tenantId": "platform-admin",
        "tenantName": "Platform",
        "name": "Super Admin",
        "email": "super@omni.ai",
        "hashed_password": hash_password("password123"), 
        "role": "Super Admin",
        "status": "Active",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    existing = await db.users.find_one({"email": "super@omni.ai"})
    if existing:
        print("Updating existing admin...")
        await db.users.update_one(
            {"email": "super@omni.ai"},
            {"$set": super_admin_data}
        )
    else:
        print("Creating new admin...")
        super_admin_data["id"] = f"user-{uuid.uuid4()}"
        await db.users.insert_one(super_admin_data)
        
    print("Done. Credentials: super@omni.ai / password123")

if __name__ == "__main__":
    asyncio.run(seed())
