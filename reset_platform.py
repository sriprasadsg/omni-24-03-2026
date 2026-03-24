import asyncio
import uuid
import sys
import os

# Ensure backend module is in path
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from database import connect_to_mongo, get_database

async def reset_platform():
    print("WARNING: Starting Full Platform Reset...")
    await connect_to_mongo()
    db = get_database()
    
    # 1. Clear Collections
    print("Deleting all Agents...")
    await db.agents.delete_many({})
    
    print("Deleting all Users...")
    await db.users.delete_many({})
    
    print("Deleting all Tenants...")
    await db.tenants.delete_many({})
    
    # 2. Create Exafluence Tenant
    tenant_id = "tenant_exafluence"
    reg_key = f"reg_{uuid.uuid4().hex[:16]}"
    
    tenant_doc = {
        "id": tenant_id,
        "name": "Exafluence",
        "enabledFeatures": ["all"],
        "registrationKey": reg_key
    }
    
    await db.tenants.insert_one(tenant_doc)
    print(f"✅ Created Tenant: Exafluence (ID: {tenant_id})")
    
    # 3. Create Admin User
    admin_email = "admin@exafluence.com"
    admin_pass = "AdminPass123!"
    
    user_doc = {
        "id": f"user-{uuid.uuid4().hex[:8]}",
        "email": admin_email,
        "name": "Exafluence Admin",
        "password": admin_pass,
        "role": "Super Admin",
        "tenantId": tenant_id,
        "status": "Active"
    }
    
    await db.users.insert_one(user_doc)
    print(f"✅ Created User: {admin_email} / {admin_pass}")
    
    # 4. Output Logic
    print("-" * 50)
    print(f"REGISTRATION_KEY|{reg_key}|END")
    print("-" * 50)

if __name__ == "__main__":
    asyncio.run(reset_platform())
