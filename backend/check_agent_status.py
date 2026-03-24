import asyncio
from database import connect_to_mongo, get_database
from datetime import datetime, timezone

async def check_agents():
    """Check all agents in the database"""
    await connect_to_mongo()
    db = get_database()
    
    agents = await db.agents.find({}).to_list(100)
    
    print(f"Found {len(agents)} agents in database:\n")
    
    for agent in agents:
        print(f"Agent ID: {agent.get('id', 'N/A')}")
        print(f"Hostname: {agent.get('hostname', 'N/A')}")
        print(f"Status: {agent.get('status', 'N/A')}")
        print(f"Platform: {agent.get('platform', 'N/A')}")
        print(f"Asset ID: {agent.get('assetId', 'N/A')}")
        print(f"Last Seen: {agent.get('lastSeen', 'N/A')}")
        print(f"IP Address: {agent.get('ipAddress', 'N/A')}")
        print(f"Version: {agent.get('version', 'N/A')}")
        print(f"Capabilities: {agent.get('capabilities', [])}")
        print("-" * 80)
    
    # Check how old the last heartbeat is
    now = datetime.now(timezone.utc)
    print(f"\nCurrent time: {now.isoformat()}")
    print("\nNote: Agents are marked offline if last_seen > 2 minutes ago")

if __name__ == "__main__":
    asyncio.run(check_agents())
