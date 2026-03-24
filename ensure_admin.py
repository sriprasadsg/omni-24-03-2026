import sys
import os
import asyncio
import hashlib

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "backend")))

from backend.database import connect_to_mongo, get_database

import bcrypt

def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

async def ensure_admin():
    await connect_to_mongo()
    db = get_database()
    
    # Try to hash password
    try:
        hashed = get_password_hash("admin123")
    except Exception as e:
        print(f"⚠️ Hashing failed: {e}")
        hashed = "admin123"

    user_data = {
        "email": "admin@example.com",
        "name": "Super Admin",
        "role": "Super Admin",
        "password": hashed,
        "tenantId": "default", # Or find a valid tenant
        "status": "Active"
    }
    
    # Find a valid tenant
    tenant = await db.tenants.find_one({})
    if tenant:
        user_data["tenantId"] = tenant["id"]
        user_data["tenantName"] = tenant["name"]
    else:
        # Create default tenant
        t_data = {
            "id": "tenant-default",
            "name": "Default Corp",
            "enabledFeatures": ["view:dashboard", "view:agents", "view:compliance", "view:insights"]
        }
        await db.tenants.update_one({"id": "tenant-default"}, {"$set": t_data}, upsert=True)
        user_data["tenantId"] = "tenant-default"
        user_data["tenantName"] = "Default Corp"

    await db.users.update_one(
        {"email": "admin@example.com"},
        {"$set": user_data},
        upsert=True
    )
    print(f"✅ Users updated. admin@example.com / admin123 created/updated for tenant {user_data['tenantId']}")

if __name__ == "__main__":
    asyncio.run(ensure_admin())
