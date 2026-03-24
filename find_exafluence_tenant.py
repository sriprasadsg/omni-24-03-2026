import asyncio
from backend.database import get_database, connect_to_mongo

async def find_tenant():
    await connect_to_mongo()
    db = get_database()
    tenant = await db.tenants.find_one({"name": "Exafluence"})
    if tenant:
        print(f"Tenant Found: ID={tenant['id']}")
        with open("exafluence_id.txt", "w") as f:
            f.write(tenant['id'])
    else:
        print("Tenant 'Exafluence' NOT found.")

if __name__ == "__main__":
    asyncio.run(find_tenant())
