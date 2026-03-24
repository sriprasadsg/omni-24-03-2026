import sys
import os
import asyncio
sys.path.append(os.path.abspath("backend"))

from backend.database import connect_to_mongo, get_database

async def check():
    await connect_to_mongo()
    db = get_database()
    
    # Get the first tenant (assuming single tenant for now or I'll list all)
    tenants = await db.tenants.find().to_list(length=10)
    
    for t in tenants:
        print(f"Tenant: {t.get('name')} (ID: {t.get('id')})")
        features = t.get('enabledFeatures', [])
        print(f"Enabled Features: {len(features)}")
        print(f"  - view:compliance: {'YES' if 'view:compliance' in features else 'NO'}")
        print(f"  - view:insights: {'YES' if 'view:insights' in features else 'NO'}")
        print(f"  - view:agents: {'YES' if 'view:agents' in features else 'NO'}")
        print(f"  - view:network: {'YES' if 'view:network' in features else 'NO'}")
        
if __name__ == "__main__":
    asyncio.run(check())
