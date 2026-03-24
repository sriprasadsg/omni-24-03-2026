import asyncio
import sys
sys.path.append('backend')
from database import connect_to_mongo, get_database
import uuid

async def create_tenant():
    await connect_to_mongo()
    db = get_database()
    
    tenant_id = "tenant_sriprasad001"
    name = "Sriprasad SG"
    
    # Create Tenant
    await db.tenants.update_one(
        {"id": tenant_id},
        {"$set": {
            "name": name,
            "subscriptionTier": "Enterprise",
            "enabledFeatures": ["all"],
            "registrationKey": f"reg_{uuid.uuid4().hex[:16]}"
        }},
        upsert=True
    )
    print(f"Created Tenant: {tenant_id}")

if __name__ == "__main__":
    asyncio.run(create_tenant())
