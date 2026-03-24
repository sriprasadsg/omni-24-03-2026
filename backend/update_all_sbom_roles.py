import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def update_all_roles():
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client.omni_agent_db
    
    # Update ALL 'admin' roles
    res1 = await db.roles.update_many(
        {"name": "admin"},
        {"$addToSet": {"permissions": {"$each": ["view:sbom", "manage:sbom"]}}}
    )
    
    # Update ALL 'Tenant Admin' roles
    res2 = await db.roles.update_many(
        {"name": "Tenant Admin"},
        {"$addToSet": {"permissions": {"$each": ["view:sbom", "manage:sbom"]}}}
    )
    
    # Update ALL 'Super Admin' roles just in case
    res3 = await db.roles.update_many(
        {"name": {"$in": ["Super Admin", "super_admin", "superadmin"]}},
        {"$addToSet": {"permissions": {"$each": ["view:sbom", "manage:sbom", "*"]}}}
    )
    
    # Update ALL 'user' (view only)
    res4 = await db.roles.update_many(
        {"name": "user"},
        {"$addToSet": {"permissions": {"$each": ["view:sbom"]}}}
    )
    
    print(f"Roles updated across all tenants. Admin: {res1.modified_count}, Tenant Admin: {res2.modified_count}, Super Admin: {res3.modified_count}")

asyncio.run(update_all_roles())
