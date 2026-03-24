
import asyncio
import sys
sys.path.append('backend')
from database import connect_to_mongo, get_database

async def fix_tenant():
    await connect_to_mongo()
    db = get_database()
    print("Fixing agent tenant ID...")
    # Update Agent
    res_agent = await db.agents.update_one(
        {"hostname": "EILT0197"}, 
        {"$set": {"tenantId": "tenant_sriprasad001"}}
    )
    # Update Asset
    res_asset = await db.assets.update_one(
        {"hostname": "EILT0197"}, 
        {"$set": {"tenantId": "tenant_sriprasad001"}}
    )
    print(f"Agent Matched: {res_agent.matched_count}, Modified: {res_agent.modified_count}")
    print(f"Asset Matched: {res_asset.matched_count}, Modified: {res_asset.modified_count}")

if __name__ == "__main__":
    asyncio.run(fix_tenant())
