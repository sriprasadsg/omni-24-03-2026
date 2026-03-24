import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from pprint import pprint, pformat

# Manual connection setup
MONGODB_URL = "mongodb://127.0.0.1:27017" 
DATABASE_NAME = "ai_platform"

async def inspect_orphans():
    output = []
    output.append(f"Connecting to {MONGODB_URL}...")
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DATABASE_NAME]
    
    # 1. Inspect 'asset-TEST-WIN-EVIDENCE' in assets collection
    output.append("\n--- Inspecting 'asset-TEST-WIN-EVIDENCE' in assets ---")
    asset = await db.assets.find_one({"id": "asset-TEST-WIN-EVIDENCE"})
    if asset:
        output.append(pformat(asset))
    else:
        output.append("Asset 'asset-TEST-WIN-EVIDENCE' NOT FOUND in 'assets' collection.")

    # 2. Inspect compliance records linked to this asset
    output.append("\n--- Inspecting compliance records for 'asset-TEST-WIN-EVIDENCE' ---")
    cursor = db.asset_compliance.find({"assetId": "asset-TEST-WIN-EVIDENCE"})
    compliance_records = await cursor.to_list(length=100)
    output.append(f"Found {len(compliance_records)} compliance records.")
    for record in compliance_records[:3]: # Show first 3
        output.append(pformat(record))

    # 3. Check for any agents linked to this asset
    output.append("\n--- Inspecting agents linked to 'asset-TEST-WIN-EVIDENCE' ---")
    cursor = db.agents.find({"assetId": "asset-TEST-WIN-EVIDENCE"})
    agents = await cursor.to_list(length=100)
    output.append(f"Found {len(agents)} agents.")
    for agent in agents:
        output.append(pformat(agent))

    with open("backend/orphan_debug_output.txt", "w") as f:
        f.write("\n".join(output))
    
    client.close()

if __name__ == "__main__":
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(inspect_orphans())
    except Exception as e:
        print(f"Error: {e}")
