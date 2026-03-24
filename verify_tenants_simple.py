
import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))

import asyncio
from database import get_database, connect_to_mongo

async def verify():
    await connect_to_mongo()
    db = get_database()
    tenants = await db.tenants.find({}, {"_id":0, "name":1, "subscriptionTier":1}).to_list(100)
    print("FINAL TENANT LIST:")
    for t in tenants:
        print(f"Name: {t.get('name')}, Tier: {t.get('subscriptionTier')}")

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(verify())
