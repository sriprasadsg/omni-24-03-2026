"""
Enable compliance_enforcement capability for agent and trigger data collection
"""
import asyncio
import sys
from database import connect_to_mongo, get_database

async def enable_and_trigger_compliance():
    await connect_to_mongo()
    db = get_database()
    
    hostname = sys.argv[1] if len(sys.argv) > 1 else "EILT0197"
    
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
        print("✅ Added compliance_enforcement capability to agent")
    else:
        print("ℹ️  Agent already has compliance_enforcement enabled")
    
    # 2. Check if agent is online
    agent = await db.agents.find_one({"hostname": hostname})
    if agent:
        status = agent.get('status', 'Unknown')
        last_seen = agent.get('lastSeen', 'Never')
        print(f"📊 Agent status: {status}")
        print(f"🕐 Last seen: {last_seen}")
        
        if status != 'Online':
            print(f"\n⚠️  Agent is {status}. Start the agent to collect compliance data.")
            print("   To start agent: python agent/agent.py")
    
    # 3. Create a test instruction for the agent to run compliance check
    print("\n💡 To collect compliance data:")
    print("   1. Ensure agent is running: python agent/agent.py")
    print("   2. Agent will collect compliance data on next heartbeat (60s interval)")
    print("   3. Or restart agent to trigger immediate collection")
    
    print("\n📋 After agent collects data, run:")
    print("   python backend/trigger_compliance_check.py --tenant_id all")

if __name__ == "__main__":
    asyncio.run(enable_and_trigger_compliance())
