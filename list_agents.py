import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017')
    db = client['omni_platform']
    agents = await db.agents.find().to_list(100)
    if not agents:
        print("No agents found in database.")
    for a in agents:
        print(f"Agent: {a.get('hostname')} Status: {a.get('status')} ID: {a.get('id')}")
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
