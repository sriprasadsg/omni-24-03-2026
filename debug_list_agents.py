import asyncio
from backend.database import connect_to_mongo, get_database
from backend.models import Agent

async def list_agents():
    await connect_to_mongo()
    db = get_database()
    agents = await db.agents.find().to_list(None)
    print(f"Total Agents: {len(agents)}")
    for a in agents:
        print(f"ID: {a.get('id')}, Tenant: {a.get('tenantId')}, Host: {a.get('hostname')}, IP: {a.get('ipAddress')}")

if __name__ == "__main__":
    asyncio.run(list_agents())
