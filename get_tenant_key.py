import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

import asyncio
from database import connect_to_mongo, get_database

async def get_key():
    await connect_to_mongo()
    db = get_database()
    
    tenant_id = "tenant_test_123"
    tenant = await db.tenants.find_one({"id": tenant_id})
    
    if tenant:
        print(f"Tenant: {tenant.get('name')}")
        print(f"ID: {tenant.get('id')}")
        key = tenant.get('registrationKey')
        if not key:
            print("Key: NOT FOUND - Generating one...")
            import uuid
            new_key = f"reg_{uuid.uuid4().hex[:16]}"
            await db.tenants.update_one(
                {"id": tenant_id},
                {"$set": {"registrationKey": new_key}}
            )
            print(f"NEW KEY GENERATED: {new_key}")
        else:
            print(f"Key: {key}")
    else:
        print("Tenant not found")
        
    await connect_to_mongo()

if __name__ == "__main__":
    asyncio.run(get_key())
