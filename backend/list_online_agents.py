from database import get_database, connect_to_mongo
import asyncio

async def list_online_agents():
    await connect_to_mongo()
    db = get_database()
    
    online_agents = await db.agents.find({"status": "Online"}).to_list(length=100)
    print(f"Found {len(online_agents)} online agents:")
    for agent in online_agents:
        print(f"- Hostname: {agent.get('hostname')}, AgentID: {agent.get('id')}, IP: {agent.get('ipAddress')}")

asyncio.run(list_online_agents())
