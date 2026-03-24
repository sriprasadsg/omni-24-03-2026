
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import json

async def main():
    uri = "mongodb://localhost:27017"
    db_name = "omni_platform"
    client = AsyncIOMotorClient(uri)
    db = client[db_name]
    
    asset_id = "asset-EILT0197"
    print(f"Checking asset: {asset_id}")
    
    asset = await db.assets.find_one({"id": asset_id})
    if asset:
        print(f"Asset found: {asset.get('hostname')}")
        print(f"Software count: {len(asset.get('installedSoftware', []))}")
        print("Current Metrics:")
        print(json.dumps(asset.get('currentMetrics', {}), indent=2))
        
        # Also check agent status in agents collection
        agent = await db.agents.find_one({"id": "agent-EILT0197"})
        if agent:
             print(f"Agent Status: {agent.get('status')} (Last Seen: {agent.get('lastSeen')})")
        else:
             # Try search by hostname if ID differs
             agent = await db.agents.find_one({"hostname": "EILT0197"})
             if agent:
                 print(f"Agent (by Hostname) Status: {agent.get('status')} (Last Seen: {agent.get('lastSeen')})")
    else:
        print("Asset not found!")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
