import sys
import os
import asyncio

# Setup API path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from database import connect_to_mongo, get_database

async def main():
    target_tenant = sys.argv[1] if len(sys.argv) > 1 else None
    
    await connect_to_mongo()
    db = get_database()
    
    if target_tenant:
        print(f"Searching for tenant: {target_tenant}")
        tenant = await db.tenants.find_one({"id": target_tenant})
    else:
        print("No tenant ID provided. Listing all:")
        async for t in db.tenants.find():
            print(f"- {t.get('id')} ({t.get('name')}) | Key: {t.get('registrationKey')}")
        return

    if tenant:
        print(f"Key: {tenant.get('registrationKey')}")
    else:
        print("Tenant not found.")

if __name__ == "__main__":
    asyncio.run(main())
