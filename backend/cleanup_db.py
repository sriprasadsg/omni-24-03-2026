
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def cleanup():
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017')
    db = client['omni_platform']
    r_assets = await db.assets.delete_many({})
    r_agents = await db.agents.delete_many({})
    print(f"Cleanup complete: Deleted {r_assets.deleted_count} assets and {r_agents.deleted_count} agents")
    client.close()

if __name__ == "__main__":
    asyncio.run(cleanup())
