import asyncio
from database import connect_to_mongo, get_database, close_mongo_connection
from tenant_context import set_tenant_id

async def update_rbac():
    await connect_to_mongo()
    # DB-F10: roles is no longer isolation-exempt; this is a one-off
    # maintenance script editing the shared platform-wide "Tenant Admin"
    # role definition, so it needs the platform-admin bypass context —
    # the same pattern app_startup.py's role-seeding routines use.
    set_tenant_id("platform-admin")
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
