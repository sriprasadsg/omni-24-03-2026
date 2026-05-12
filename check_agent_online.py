import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017')
    db = client['omni_platform']
    agent = await db.agents.find_one({'status': 'Online'})
    print(f'Online Agent: {agent.get("hostname") if agent else "None"}')
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
