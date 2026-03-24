
import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))

import asyncio
from database import get_database, connect_to_mongo

async def delete_all():
    await connect_to_mongo()
    db = get_database()
    
    print("Deleting all Assets...")
    result_assets = await db.assets.delete_many({})
    print(f"Deleted {result_assets.deleted_count} assets.")
    
    print("Deleting all Agents...")
    result_agents = await db.agents.delete_many({})
    print(f"Deleted {result_agents.deleted_count} agents.")

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(delete_all())
