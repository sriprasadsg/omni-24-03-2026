import asyncio
import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from dotenv import load_dotenv
load_dotenv()

from dotenv import load_dotenv
load_dotenv()

from database import get_database, connect_to_mongo

async def check_data():
    await connect_to_mongo()
    db = get_database()
    
    # 1. Check Agents
    print("\n--- AGENTS ---")
    agents = await db.agents.find({}, {"_id": 0, "id": 1, "hostname": 1, "status": 1}).to_list(10)
    for a in agents:
        print(a)
        
    # 2. Check Assets
    print("\n--- ASSETS ---")
    assets = await db.assets.find({}, {"_id": 0, "id": 1, "hostname": 1, "type": 1}).to_list(10)
    for a in assets:
        print(a)

    # 3. Check Capabilities
    print("\n--- CAPABILITIES ---")
    caps = await db.agent_capabilities.find({}, {"_id": 0, "agent_id": 1, "capabilities": 1}).to_list(10)
    for c in caps:
        print(c)

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    loop.run_until_complete(check_data())
