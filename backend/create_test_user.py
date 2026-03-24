import asyncio
from database import connect_to_mongo, get_database
import uuid

async def create_user():
    await connect_to_mongo()
    db = get_database()
    
    email = "testadmin@example.com"
    password = "TestPass123!" 
    
    # 1. Ensure Tenant
    tenant_id = "tenant_test_123"
    await db.tenants.update_one(
        {"id": tenant_id},
        {"$set": {"name": "Test Corp", "enabledFeatures": ["all"]}},
        upsert=True
    )
    
    # 2. Upsert User with Plaintext Password (enabled by app.py BYPASS logic)
    user_doc = {
        "id": f"user-{uuid.uuid4().hex[:8]}",
        "email": email,
        "name": "Test Admin",
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
    
    print(f"Created/Updated User: {email} / {password}")

if __name__ == "__main__":
    asyncio.run(create_user())
