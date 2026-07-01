import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def update_roles():
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client.omni_agent_db
    
    # Update 'admin'
    res1 = await db.roles.update_one(
        {"name": "admin"},
        {"$addToSet": {"permissions": {"$each": ["view:sbom", "manage:sbom"]}}}
    )
    
    # Update 'Tenant Admin'
    res2 = await db.roles.update_one(
        {"name": "Tenant Admin"},
        {"$addToSet": {"permissions": {"$each": ["view:sbom", "manage:sbom"]}}}
    )
    
    # Update 'user' (view only)
    res3 = await db.roles.update_one(
        {"name": "user"},
        {"$addToSet": {"permissions": {"$each": ["view:sbom"]}}}
    )
    
    print(f"Roles updated. Admin DB Matches: {res1.matched_count}, Tenant Admin DB Matches: {res2.matched_count}")

asyncio.run(update_roles())
