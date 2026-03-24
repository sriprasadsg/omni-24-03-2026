
import asyncio
from backend.database import get_database, connect_to_mongo

async def update_permissions():
    await connect_to_mongo()
    db = get_database()
    
    # 1. Update Super Admin Role
    # Check if 'manage:pricing' exists, if not add it
    await db.roles.update_one(
        {"name": "Super Admin"},
        {"$addToSet": {"permissions": "manage:pricing"}}
    )
    print("Added manage:pricing to Super Admin role.")

if __name__ == "__main__":
    asyncio.run(update_permissions())
