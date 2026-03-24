
import asyncio
import os
import motor.motor_asyncio

# Direct DB connection
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = "enterprise_agent_db"

async def list_tenants_and_users():
    print("Connecting to DB...")
    client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    
    print("\n--- TENANTS ---")
    async for t in db.tenants.find():
        print(f"Name: {t.get('name')}, ID: {t.get('id')}")
        
    print("\n--- USERS ---")
    async for u in db.users.find():
        print(f"Email: {u.get('email')}, TenantID: {u.get('tenantId')}, Role: {u.get('role')}")

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(list_tenants_and_users())
