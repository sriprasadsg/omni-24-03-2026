import asyncio
from database import mongodb, connect_to_mongo, close_mongo_connection

async def check():
    await connect_to_mongo()
    tenant = await mongodb.db.tenants.find_one()
    print(f"TENANT_ID: {tenant.get('id') if tenant else 'NONE'}")
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(check())
