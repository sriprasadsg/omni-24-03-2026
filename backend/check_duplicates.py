
from database import get_database, connect_to_mongo
import asyncio

async def check_duplicates():
    await connect_to_mongo()
    db = get_database()
    agents = await db.agents.find().to_list(100)
    print(f"Total Agents: {len(agents)}")
    for a in agents:
        print(f"Agent Hostname: {a.get('hostname')}, ID: {a.get('id')}, AssetID: {a.get('assetId')}, Status: {a.get('status')}")

if __name__ == "__main__":
    asyncio.run(check_duplicates())
