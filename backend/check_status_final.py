import asyncio
from database import get_database

async def check():
    from database import connect_to_mongo
    await connect_to_mongo()
    db = get_database()
    print("--- Agents in DB ---")
    async for agent in db.agents.find():
        st = agent.get('status')
        print(f"ID: {repr(agent.get('id'))}")
        print(f"Status: {repr(st)}")
        print(f"Equality Check ('Online'): {st == 'Online'}")
        print(f"Type: {type(st)}")
        print(f"Ords: {[ord(c) for c in st] if st else []}")
        print("-" * 20)
    
    print("\n--- Tenants in DB ---")
    async for tenant in db.tenants.find():
        print(f"ID: {tenant.get('id')}")
        print(f"Name: {tenant.get('name')}")
        print("-" * 20)

    print("\n--- Super User in DB ---")
    user = await db.users.find_one({"email": "super@omni.ai"})
    if user:
        print(f"Email: {user.get('email')}")
        print(f"TenantID: {user.get('tenantId')}")
        print(f"Role: {user.get('role')}")

if __name__ == "__main__":
    asyncio.run(check())
