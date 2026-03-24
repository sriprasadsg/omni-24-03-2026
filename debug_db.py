import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["omni_platform"]
    
    print("--- Tenants ---")
    tenants = await db.tenants.find({}).to_list(length=10)
    for t in tenants:
        print(f"Tenant: {t.get('name')} (ID: {t.get('id')}) - Key: {t.get('registrationKey')}")
        if t.get('name') == 'Exafluence':
            with open("key_verify.txt", "w") as f:
                f.write(t.get('registrationKey'))
        
    print("--- Agents ---")
    agents = await db.agents.find({}).to_list(length=100)
    print(f"Total Agents: {len(agents)}")
    for a in agents:
        print(f"Agent: {a.get('hostname')} (ID: {a.get('id')}) - Tenant: {a.get('tenantId')} - Status: {a.get('status')} - LastSeen: {a.get('lastSeen')}")

    print("\n--- Users ---")
    super_admin = await db.users.find_one({"email": "super@omni.ai"})
    if super_admin:
        print(f"Super Admin: Role={super_admin.get('role')}, Tenant={super_admin.get('tenantId')}")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
