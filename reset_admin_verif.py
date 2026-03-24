import asyncio
import os
import sys

# Ensure backend is in path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from database import connect_to_mongo, get_database, close_mongo_connection
from tenant_context import set_tenant_id
from auth_utils import hash_password

async def reset_admin_password():
    await connect_to_mongo()
    set_tenant_id("platform-admin")
    db = get_database()
    
    # Use native hash_password from auth_utils
    hp = hash_password("password123")
    
    # Update field 'password' as per registration logic
    result = await db.users.update_one(
        {"email": "super@omni.ai"},
        {"$set": {"password": hp}}
    )
    
    print(f"Password reset result: {result.modified_count} updated.")
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(reset_admin_password())
