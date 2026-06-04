
import asyncio
from database import connect_to_mongo, get_database

async def main():
    try:
        await connect_to_mongo()
        db = get_database()
        tenant_id = "tenant_82dda0f33bc4"
        tenant = await db.tenants.find_one({"id": tenant_id})
        print(f"Tenant {tenant_id}: {tenant}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
