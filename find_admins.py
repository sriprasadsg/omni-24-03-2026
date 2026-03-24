import asyncio
import os
import sys

# Ensure backend is in path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from database import connect_to_mongo, get_database, close_mongo_connection
from tenant_context import set_tenant_id

async def find_admin():
    await connect_to_mongo()
    
    # Set context to bypass hardening for this debug script
    set_tenant_id("platform-admin")
    
    db = get_database()
    
    # Check users
    users = await db.users.find({}).to_list(length=100)
    print("\n--- USERS IN DATABASE ---")
    for u in users:
        print(f"ID: {u.get('id')}, Email: {u.get('email')}, Tenant: {u.get('tenantId')}, Roles: {u.get('roles')}")

    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(find_admin())
