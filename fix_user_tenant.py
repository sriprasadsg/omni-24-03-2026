import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def fix_user_tenant():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client.omni_platform
    
    # 1. Find the tenant
    tenant = await db.tenants.find_one({"name": {"$regex": "xafleucne", "$options": "i"}})
    if not tenant:
        print("❌ No tenant found matching 'exafleucne'!")
        client.close()
        return
    
    tenant_id = tenant.get("id")
    tenant_name = tenant.get("name")
    print(f"Found tenant: {tenant_name} (ID: {tenant_id})")
    
    # 2. Update the user
    result = await db.users.update_one(
        {"email": "admin@ex afleucne.com"},
        {"$set": {"tenantId": tenant_id, "tenantName": tenant_name}}
    )
    
    print(f"✅ Updated {result.modified_count} user(s)")
    
    # 3. Verify
    user = await db.users.find_one({"email": "admin@exafleucne.com"})
    if user:
        print(f"User now has:")
        print(f"  tenantId: {user.get('tenantId')}")
        print(f"  tenantName: {user.get('tenantName')}")
    
    client.close()

asyncio.run(fix_user_tenant())
