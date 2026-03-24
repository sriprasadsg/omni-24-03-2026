import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))
import asyncio
from database import connect_to_mongo, get_database

async def check_agents():
    await connect_to_mongo()
    db = get_database()
    agents = await db.agents.find({}).to_list(length=100)
    print(f"Total Agents: {len(agents)}")
    for a in agents:
        print(f"Agent: {a.get('hostname')} | ID: {a.get('id')} | Tenant: {a.get('tenantId')} | Status: {a.get('status')}")

if __name__ == "__main__":
    asyncio.run(check_agents())
