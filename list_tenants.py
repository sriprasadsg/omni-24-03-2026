import asyncio
import sys
sys.path.append('backend')
from database import connect_to_mongo, get_database

async def list_tenants():
    await connect_to_mongo()
    db = get_database()
    tenants = await db.tenants.find().to_list(length=100)
    for t in tenants:
        print(f"ID: {t.get('id')}, Name: {t.get('name')}")

if __name__ == "__main__":
    asyncio.run(list_tenants())
