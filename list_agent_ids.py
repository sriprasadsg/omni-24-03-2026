from motor.motor_asyncio import AsyncIOMotorClient
import asyncio

async def run():
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client['omni_platform']
    agents = await db.agents.find({}, {'id': 1}).to_list(length=10)
    print([a['id'] for a in agents])

if __name__ == "__main__":
    asyncio.run(run())
