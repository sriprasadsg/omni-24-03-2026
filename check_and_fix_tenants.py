
import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))

import asyncio
from database import get_database, connect_to_mongo, close_mongo_connection

async def check_and_fix_tenants():
    await connect_to_mongo()
    db = get_database()
    
    print("--- Current Tenants ---")
    tenants = await db.tenants.find({}).to_list(length=100)
    
    exafluence_found = False
    
    for t in tenants:
        print(f"ID: {t.get('id')}, Name: {t.get('name')}, Tier: {t.get('subscriptionTier')}")
        
        if t.get('name') == 'Exafluence':
            exafluence_found = True
            if not t.get('subscriptionTier'):
                print(f"FIXING: Setting subscriptionTier='Enterprise' for Exafluence")
                await db.tenants.update_one(
                    {"_id": t["_id"]},
                    {"$set": {"subscriptionTier": "Enterprise"}}
                )
            
    # Remove obvious mocks
    mock_names = ["Acme", "Omni", "Omni AI"]
    result = await db.tenants.delete_many({"name": {"$in": mock_names}})
    if result.deleted_count > 0:
        print(f"Deleted {result.deleted_count} mock tenants: {mock_names}")

    print("--- Updated Tenants ---")
    tenants = await db.tenants.find({}).to_list(length=100)
    for t in tenants:
         print(f"ID: {t.get('id')}, Name: {t.get('name')}, Tier: {t.get('subscriptionTier')}")
         
    await close_mongo_connection()

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(check_and_fix_tenants())
    loop.close()
