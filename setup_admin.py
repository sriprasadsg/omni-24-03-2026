
import sys
import asyncio
sys.path.append('backend')

from backend.database import connect_to_mongo, get_database
import uuid

async def setup_admin():
    print("Connecting to MongoDB...")
    await connect_to_mongo()
    db = get_database()
    
    email = "admin@example.com"
    password = "admin"
    tenant_id = "tenant_default"
    
    # Ensure Tenant
    print(f"Upserting Tenant: {tenant_id}")
    await db.tenants.update_one(
        {"id": tenant_id},
        {"$set": {
            "name": "Default Corp", 
            "enabledFeatures": ["all"],
            "registrationKey": "reg_default_key"
        }},
        upsert=True
    )
    
    # Upsert User
    print(f"Upserting User: {email}")
    user_doc = {
        "id": "user-admin",
        "email": email,
        "username": email, # Fallback
        "name": "Super Admin",
        "password": password, 
        "role": "Super Admin",
        "tenantId": tenant_id,
        "status": "Active"
    }
    
    await db.users.update_one(
        {"email": email},
        {"$set": user_doc},
        upsert=True
    )
    
    print("User setup complete.")

if __name__ == "__main__":
    asyncio.run(setup_admin())
