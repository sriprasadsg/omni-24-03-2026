"""
Enable compliance_enforcement capability for agent and trigger data collection
"""
import asyncio
from database import connect_to_mongo, get_database

async def enable_and_trigger_compliance():
    await connect_to_mongo()
    db = get_database()
    
    hostname = "EILT0197"
    
    print(f"🔧 Enabling compliance_enforcement for {hostname}...")
    
    # 1. Ensure agent has capability enabled
    result = await db.agents.update_one(
        {"hostname": hostname},
        {
            "$addToSet": {
                "agentCapabilities": "compliance_enforcement"
            }
        }
    )
    
    if result.modified_count > 0:
        print(f"✅ Added compliance_enforcement capability to agent")
    else:
        print(f"ℹ️  Agent already has compliance_enforcement enabled")
    
    # 2. Check if agent is online
    agent = await db.agents.find_one({"hostname": hostname})
    if agent:
        status = agent.get('status', 'Unknown')
        last_seen = agent.get('lastSeen', 'Never')
        print(f"📊 Agent status: {status}")
        print(f"🕐 Last seen: {last_seen}")
        
        if status != 'Online':
            print(f"\n⚠️  Agent is {status}. Start the agent to collect compliance data.")
            print(f"   To start agent: python agent/agent.py")
    
    # 3. Create a test instruction for the agent to run compliance check
    print(f"\n💡 To collect compliance data:")
    print(f"   1. Ensure agent is running: python agent/agent.py")
    print(f"   2. Agent will collect compliance data on next heartbeat (60s interval)")
    print(f"   3. Or restart agent to trigger immediate collection")
    
    print(f"\n📋 After agent collects data, run:")
    print(f"   python backend/trigger_compliance_check.py --tenant_id all")

if __name__ == "__main__":
    asyncio.run(enable_and_trigger_compliance())
