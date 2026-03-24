import asyncio
import os
import sys

# Ensure backend is in path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from database import connect_to_mongo, get_database, close_mongo_connection
from tenant_context import set_tenant_id

async def verify_admin_fields():
    await connect_to_mongo()
    set_tenant_id("platform-admin")
    db = get_database()
    
    user = await db.users.find_one({"email": "super@omni.ai"})
    if user:
        print("\n--- ADMIN FIELDS ---")
        print(f"ID: {user.get('id')}")
        print(f"Email: {user.get('email')}")
        print(f"Has 'password' field: {'password' in user}")
        print(f"Has 'hashed_password' field: {'hashed_password' in user}")
        
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(verify_admin_fields())
