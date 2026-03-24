
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import json

async def check_raw_agent():
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017')
    db = client['omni_platform']
    agent = await db.agents.find_one({'hostname': 'EILT0197'})
    if agent:
        # Convert ObjectId to string for JSON serialization
        if '_id' in agent:
            agent['_id'] = str(agent['_id'])
        print(json.dumps(agent, indent=2))
    else:
        print("Agent not found")
    client.close()

if __name__ == "__main__":
    asyncio.run(check_raw_agent())
