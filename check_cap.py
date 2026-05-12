import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))
import asyncio
from database import connect_to_mongo, get_database

async def check_caps():
    await connect_to_mongo()
    db = get_database()
    agents = await db.agents.find({}).to_list(length=100)
    for a in agents:
        caps = a.get('capabilities', [])
        print(f"Agent {a.get('hostname')}: {len(caps)} capabilities")
        for i, c in enumerate(caps):
            print(f"  {i+1}. {c}")

if __name__ == "__main__":
    asyncio.run(check_caps())
