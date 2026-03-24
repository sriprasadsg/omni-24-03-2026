import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def check_user_tenant():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client.omni_platform
    
    # 1. Find the user
    user = await db.users.find_one({"email": "admin@exafleucne.com"})
    if user:
        print("User found:")
        print(f"  Email: {user.get('email')}")
        print(f"  Username: {user.get('username')}")
        print(f"  tenantId: {user.get('tenantId')}")
        print(f"  role: {user.get('role')}")
    else:
        print("User NOT found in database")
    
    # 2. Find tenants with "exafleucne" in name
    print("\n=== Tenants matching 'exafleucne' ===")
    async for tenant in db.tenants.find({"name": {"$regex": "xafleucne", "$options": "i"}}):
        print(f"  ID: {tenant.get('id')}")
        print(f"  Name: {tenant.get('name')}")
        print(f"  registrationKey: {tenant.get('registrationKey')}")
    
    # 3. Check SBOMs
    print("\n=== All SBOMs ===")
    async for sbom in db.sboms.find():
        print(f"  ID: {sbom.get('id')}")
        print(f"  Tenant: {sbom.get('tenantId')}")
        print(f"  App: {sbom.get('applicationName')}")
    
    client.close()

asyncio.run(check_user_tenant())
