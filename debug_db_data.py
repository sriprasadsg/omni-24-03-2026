import sys
import os
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

async def debug_db():
    print("Connecting to database...")
    from database import connect_to_mongo, get_database
    await connect_to_mongo()
    db = get_database()
    
    # 1. List Tenants
    print("\n--- Tenants ---")
    async for tenant in db.tenants.find({}):
        print(f"ID: {tenant.get('id')}, Name: {tenant.get('name')}")

    # 2. List Assets (ALL)
    # Use raw collection to bypass tenant injection if needed, 
    # but get_database returns TenantIsolatedDatabase.
    # To bypass, we can access _db directly or just use "platform-admin" context?
    # Actually locally get_database() with no context returns NO filter (except line 15 check implies passing it through).
    # Wait, line 16: if not tenant_id ... return filter_query.
    # So if I don't set context, I verify what seeded.
    
    print("\n--- Assets (Raw View) ---")
    # Check if the asset exists
    async for asset in db.assets.find({}):
        print(f"ID: {asset.get('id')}, Host: {asset.get('hostname')}, Tenant: {asset.get('tenantId')}")

    # 3. List Agents
    print("\n--- Agents ---")
    async for agent in db.agents.find({}):
         print(f"ID: {agent.get('id')}, Tenant: {agent.get('tenantId')}")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(debug_db())
