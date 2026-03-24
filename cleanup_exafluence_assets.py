
import asyncio
import sys
import os

# Ensure backend directory is in path for imports
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from database import connect_to_mongo, mongodb, get_database

async def cleanup():
    await connect_to_mongo()
    
    # 1. Find Exafluence Tenant
    tenant = await mongodb.db.tenants.find_one({"name": "Exafluence"})
    if not tenant:
        print("Tenant 'Exafluence' not found.")
        # Fallback search by case insensitive or part
        tenant = await mongodb.db.tenants.find_one({"name": {"$regex": "exafluence", "$options": "i"}})
        
    if not tenant:
        print("Could not locate Exafluence tenant.")
        return

    tenant_id = tenant['id']
    print(f"Target Tenant: {tenant['name']} ({tenant_id})")
    
    # 2. Find Assets
    assets = await mongodb.db.assets.find({"tenantId": tenant_id}).to_list(100)
    print(f"Found {len(assets)} assets for this tenant.")
    
    # 3. Delete Assets
    for asset in assets:
        print(f"Deleting asset: {asset.get('hostname', 'unknown')} ({asset['id']})")
        await mongodb.db.assets.delete_one({"id": asset['id']})
        
        # Check for linked agent and delete if exists
        agent = await mongodb.db.agents.find_one({"assetId": asset['id']})
        if agent:
            print(f"  > Also deleting linked agent: {agent.get('hostname')} ({agent['id']})")
            await mongodb.db.agents.delete_one({"id": agent['id']})
    
    # 4. Check for remaining agents (orphaned)
    agents = await mongodb.db.agents.find({"tenantId": tenant_id}).to_list(100)
    if len(agents) > 0:
        print(f"Found {len(agents)} remaining agents for this tenant.")
        for agent in agents:
             print(f"Deleting agent: {agent.get('hostname')} ({agent['id']})")
             await mongodb.db.agents.delete_one({"id": agent['id']})
             
    print("Cleanup complete.")

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(cleanup())
