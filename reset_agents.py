
import asyncio
import os
import motor.motor_asyncio
from pymongo import MongoClient
import uuid

# Direct DB connection to avoid backend app dependencies
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = "omni_platform"

async def reset_and_get_tenant():
    print("Connecting to DB...")
    client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    # 1. Delete all agents
    print("Deleting all agents...")
    res_agents = await db.agents.delete_many({})
    print(f"Deleted {res_agents.deleted_count} agents.")
    
    # 2. Delete all assets
    print("Deleting all assets...")
    res_assets = await db.assets.delete_many({})
    print(f"Deleted {res_assets.deleted_count} assets.")
    
    # 3. Find 'Exafluence' tenant
    print("Searching for 'Exafluence' tenant...")
    tenant = await db.tenants.find_one({"name": {"$regex": "Exafluence", "$options": "i"}})
    
    if tenant:
        print(f"FOUND TENANT: {tenant.get('name')}")
        print(f"TENANT ID: {tenant.get('id')}")
        with open("exafluence_tenant_id.txt", "w") as f:
            f.write(tenant.get('id'))
    else:
        print("ERROR: Tenant 'Exafluence' not found.")
        print("Available Tenants:")
        async for t in db.tenants.find():
            print(f" - {t.get('name')} ({t.get('id')})")

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(reset_and_get_tenant())
