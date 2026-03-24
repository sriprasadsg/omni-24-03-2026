
import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))

import asyncio
from database import get_database, connect_to_mongo
import uuid
from datetime import datetime, timezone

async def create_tenants():
    await connect_to_mongo()
    db = get_database()
    
    tenants = [
        {"name": "Sri Prasad Enterprise", "subscriptionTier": "Enterprise"},
        {"name": "Exafluence", "subscriptionTier": "Pro"},
        {"name": "Test Org", "subscriptionTier": "Free"}
    ]
    
    for t in tenants:
        exists = await db.tenants.find_one({"name": t["name"]})
        if not exists:
            tenant_doc = {
                "id": f"tenant_{uuid.uuid4().hex[:12]}",
                "name": t["name"],
                "subscriptionTier": t["subscriptionTier"],
                "registrationKey": f"reg_{uuid.uuid4().hex}",
                "enabledFeatures": ["agents", "assets"],
                "createdAt": datetime.now(timezone.utc).isoformat(),
                "updatedAt": datetime.now(timezone.utc).isoformat()
            }
            await db.tenants.insert_one(tenant_doc)
            print(f"Created tenant: {t['name']}")
        else:
            print(f"Tenant exists: {t['name']}")

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(create_tenants())
