
import asyncio
from database import connect_to_mongo, close_mongo_connection, get_database

async def debug_db():
    print("--- Debugging DB for EILT0197 ---")
    await connect_to_mongo()
    db = get_database()
    
    agent_id = "agent-EILT0197"
    
    # Check Agent
    agent = await db.agents.find_one({"id": agent_id})
    if agent:
        print(f"✅ Found Agent: {agent_id}")
        print(f"   Asset ID: {agent.get('assetId')}")
        print(f"   Meta Keys: {list(agent.get('meta', {}).keys())}")
        asset_id = agent.get('assetId')
    else:
        print(f"❌ Agent {agent_id} NOT FOUND")
        asset_id = None

    # Check Asset
    if asset_id:
        asset = await db.assets.find_one({"id": asset_id})
        if asset:
             print(f"✅ Found Linked Asset: {asset_id}")
        else:
             print(f"❌ Linked Asset {asset_id} NOT FOUND in assets collection")
    
    # Check Compliance by Agent ID directly? or Asset ID?
    # Usually compliance is linked to Asset ID.
    if asset_id:
        comp_docs = await db.asset_compliance.find({"asset_id": asset_id}).to_list(length=10)
        print(f"Compliance Docs (by Asset ID {asset_id}): {len(comp_docs)}")
    # Write to file
    with open("debug_out.txt", "w") as f:
        f.write(f"Agent ID: {agent_id}\n")
        if agent:
            f.write(f"Agent Found: Yes\n")
            f.write(f"Asset ID: {agent.get('assetId')}\n")
            f.write(f"Meta Keys: {list(agent.get('meta', {}).keys())}\n")
        else:
            f.write("Agent Found: No\n")
        
        f.write(f"Asset Found: {asset_id if asset_id else 'N/A'}\n")
        
        # Check ALL compliance docs just to see if ANY exist
        all_docs = await db.asset_compliance.count_documents({})
        f.write(f"Total Compliance Docs in DB: {all_docs}\n")
        
        # Check specific
        if asset_id:
            c1 = await db.asset_compliance.count_documents({"asset_id": asset_id})
            f.write(f"Docs for Asset ID {asset_id}: {c1}\n")
        
        c2 = await db.asset_compliance.count_documents({"asset_id": "EILT0197"})
        f.write(f"Docs for Asset ID 'EILT0197': {c2}\n")

    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(debug_db())
