import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import uuid
import datetime

async def main():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["omni_platform"]

    # 1. Cleanup
    print("Deleting all tenants...")
    await db.tenants.delete_many({})
    print("Deleting all agents...")
    await db.agents.delete_many({})
    
    # 2. Create Exafluence
    tenant_id = f"tenant_{uuid.uuid4().hex[:12]}"
    reg_key = f"reg_{uuid.uuid4().hex[:16]}"
    
    exafluence = {
        "id": tenant_id,
        "name": "Exafluence",
        "tier": "Enterprise",
        "status": "active",
        "registrationKey": reg_key,
        "created_at": datetime.datetime.utcnow().isoformat()
    }
    
    await db.tenants.insert_one(exafluence)
    print(f"Created Exafluence Tenant:")
    print(f"ID: {tenant_id}")
    print(f"Key: {reg_key}")
    
    with open("key.txt", "w") as f:
        f.write(reg_key)
    
    # 3. Check users
    super_admin = await db.users.find_one({"email": "super@omni.ai"})
    if super_admin:
        print("Super admin user exists.")
    else:
        print("WARNING: Super admin user not found.")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
