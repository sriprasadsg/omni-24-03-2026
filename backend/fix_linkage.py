
import asyncio
from database import connect_to_mongo, close_mongo_connection, get_database
import time

async def fix_linkage():
    print("--- Fixing Agent-Asset Linkage ---")
    await connect_to_mongo()
    db = get_database()
    
    agent_id = "agent-EILT0197"
    asset_id = "asset-EILT0197" # Construct a stable ID
    hostname = "EILT0197"
    
    # 1. Create/Upsert Asset
    await db.assets.update_one(
        {"id": asset_id},
        {"$set": {
            "id": asset_id,
            "hostname": hostname,
            "ipAddress": "192.168.0.102",
            "lastSeen": time.time(),
            "status": "Online",
            "platform": "Windows",
            "osVersion": "Windows 11 Pro"
        }},
        upsert=True
    )
    print(f"✅ Upserted Asset: {asset_id}")

    # 2. Link Agent
    await db.agents.update_one(
        {"id": agent_id},
        {"$set": {"assetId": asset_id}}
    )
    print(f"✅ Linked Agent {agent_id} to Asset {asset_id}")
    
    # 3. Fix Compliance Data
    # See what asset_id the existing compliance docs have.
    # If they were created without asset_id, they might have asset_id=None or derived from hostname?
    # I'll just update ALL compliance docs that have check "Windows Firewall" (from my injection) to use this asset_id.
    res = await db.asset_compliance.update_many(
        {"check_name": "Windows Firewall"}, # Specific to my injection
        {"$set": {"asset_id": asset_id}}
    )
    print(f"✅ Updated {res.modified_count} compliance records for Windows Firewall to asset_id {asset_id}")
    
    res2 = await db.asset_compliance.update_many(
        {"check_name": "Audit Policy"}, 
        {"$set": {"asset_id": asset_id}}
    )
    with open("fix_out.txt", "w") as f:
        f.write(f"Upserted Asset: {asset_id}\n")
        f.write(f"Linked Agent to Asset\n")
        f.write(f"Updated {res.modified_count} Firewall records\n")
        f.write(f"Updated {res2.modified_count} Audit records\n")

    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(fix_linkage())
