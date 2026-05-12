import asyncio
from database import connect_to_mongo, get_database, close_mongo_connection

async def update_rbac():
    await connect_to_mongo()
    db = get_database()
    
    # Get the existing Tenant Admin role
    role = await db.roles.find_one({"name": "Tenant Admin"})
    if role:
        permissions = role.get("permissions", [])
        if "view:integrations" not in permissions:
            permissions.append("view:integrations")
            await db.roles.update_one(
                {"name": "Tenant Admin"},
                {"$set": {"permissions": permissions}}
            )
            print("Updated Tenant Admin role with view:integrations")
        else:
            print("Tenant Admin role already has view:integrations")
    else:
        print("Tenant Admin role not found")
        
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(update_rbac())
