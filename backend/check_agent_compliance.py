"""
Check agent compliance data and enable if needed
"""
import asyncio
from database import connect_to_mongo, get_database

async def check_agent_compliance():
    await connect_to_mongo()
    db = get_database()
    
    # Check asset
    asset = await db.assets.find_one({'hostname': 'EILT0197'})
    if asset:
        print(f"✅ Asset found: {asset.get('hostname')}")
        meta = asset.get('meta', {})
        print(f"📊 Meta keys: {list(meta.keys())}")
        
        if 'compliance_enforcement' in meta:
            compliance_data = meta['compliance_enforcement']
            checks = compliance_data.get('compliance_checks', [])
            print(f"✅ Compliance data exists: {len(checks)} checks")
        else:
            print("❌ No compliance_enforcement data found in asset meta")
    else:
        print("❌ Asset not found")
    
    # Check agent
    agent = await db.agents.find_one({'hostname': 'EILT0197'})
    if agent:
        print(f"\n✅ Agent found: {agent.get('hostname')}")
        caps = agent.get('agentCapabilities', [])
        print(f"📦 Enabled capabilities: {caps}")
        
        if 'compliance_enforcement' in caps:
            print("✅ compliance_enforcement capability is ENABLED")
        else:
            print("❌ compliance_enforcement capability is NOT enabled")
            print("\n💡 Enable it by updating agent capabilities in the database or agent config")
    else:
        print("❌ Agent not found")

if __name__ == "__main__":
    asyncio.run(check_agent_compliance())
