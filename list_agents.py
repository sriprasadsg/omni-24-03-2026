import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "backend")))

from backend.database import connect_to_mongo, get_database
import asyncio

async def list_agents():
    await connect_to_mongo()
    db = get_database()
    
    agents = await db.agents.find().to_list(length=10)
    for agent in agents:
        print(f"Hostname: '{agent.get('hostname')}'")
        print(f"AgentID: '{agent['id']}'")
        print(f"AssetID: '{agent.get('assetId')}'")
        print(f"TenantID: '{agent.get('tenantId')}'")
        print("-" * 20)

if __name__ == "__main__":
    asyncio.run(list_agents())
