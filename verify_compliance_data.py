import sys
import os
import asyncio
sys.path.append(os.path.abspath("backend"))

from backend.database import connect_to_mongo, get_database

async def verify():
    await connect_to_mongo()
    db = get_database()
    
    agent_id = "agent-EILT0197"
    expected_asset_id = "asset-EILT0197"
    
    # 1. Check Agent Link
    agent = await db.agents.find_one({"id": agent_id})
    if not agent:
        print("❌ Agent not found")
        return
        
    actual_asset = agent.get("assetId")
    if actual_asset == expected_asset_id:
        print(f"✅ Agent correctly linked to asset: {actual_asset}")
    else:
        print(f"❌ Agent assetId mismatch. Expected {expected_asset_id}, got {actual_asset}")

    # 2. Check Asset Compliance
    cursor = db.asset_compliance.find({"assetId": expected_asset_id})
    compliance_docs = await cursor.to_list(length=100)
    
    if len(compliance_docs) > 0:
        print(f"✅ Found {len(compliance_docs)} compliance records for asset")
        print(f"Sample Doc AssetID: '{compliance_docs[0].get('assetId')}'")
    else:
        print("❌ No compliance records found in 'asset_compliance'")
        
        # Check if ANY exist
        any_doc = await db.asset_compliance.find_one({})
        if any_doc:
            print(f"⚠️ Found unrelated doc: AssetID='{any_doc.get('assetId')}'")
        else:
             print("⚠️ Collection is completely empty")
        
    # 3. Check Meta Fallback
    meta_compliance = agent.get("meta", {}).get("compliance_enforcement", {})
    if meta_compliance.get("rules"):
        print(f"✅ Agent meta has {len(meta_compliance['rules'])} compliance rules")
    else:
        print("❌ Agent meta missing compliance rules")

if __name__ == "__main__":
    asyncio.run(verify())
