import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017')
    db = client['omni_platform']
    tenants = await db.tenants.find().to_list(100)
    for t in tenants:
        print(f"Tenant: {t.get('name')} Key: {t.get('registrationKey')}")
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
