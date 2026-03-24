
import asyncio
from database import get_database, connect_to_mongo

async def main():
    await connect_to_mongo()
    db = get_database()
    
    hostname = "EILT0197"
    target_id = "agent-EILT0197"
    asset_id = "asset-EILT0197"
    
    # 1. Find all agents with hostname
    agents = await db.agents.find({"hostname": hostname}).to_list(100)
    print(f"Found {len(agents)} agents with hostname {hostname}")
    
    for a in agents:
        aid = a.get("id")
        status = a.get("status")
        asset = a.get("assetId")
        print(f" - {aid}: Status={status}, AssetID={asset}")
        
        if aid != target_id:
            print(f"   -> Deleting duplicate agent {aid}")
            await db.agents.delete_one({"id": aid})
    
    # 2. Update the target agent
    print(f"Updating {target_id} with assetId={asset_id}")
    result = await db.agents.update_one(
        {"id": target_id},
        {"$set": {"assetId": asset_id}}
    )
    print(f"Modified: {result.modified_count}")
    
    # 3. Verify
    updated = await db.agents.find_one({"id": target_id})
    print(f"Verification: {updated.get('id')} assetId is now {updated.get('assetId')}")

if __name__ == "__main__":
    asyncio.run(main())
