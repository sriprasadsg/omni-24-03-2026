import asyncio
from database import connect_to_mongo, get_database

async def check_tenants():
    """Check all tenants in the database"""
    await connect_to_mongo()
    db = get_database()
    
    tenants = await db.tenants.find({}).to_list(100)
    
    print(f"Found {len(tenants)} tenants in database:\n")
    
    for tenant in tenants:
        print(f"Tenant ID: {tenant.get('id', 'N/A')}")
        print(f"Name: {tenant.get('name', 'N/A')}")
        print(f"Subscription Tier: {tenant.get('subscriptionTier', 'N/A')}")
        print(f"Registration Key: {tenant.get('registrationKey', 'N/A')}")
        print("-" * 80)

if __name__ == "__main__":
    asyncio.run(check_tenants())
