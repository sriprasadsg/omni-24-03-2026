import motor.asyncio
import asyncio
import os
import json
from dotenv import load_dotenv

load_dotenv()

async def get_agent():
    client = motor.asyncio.AsyncIOMotorClient(os.getenv('MONGODB_URI', 'mongodb://localhost:27017'))
    db = client.omni_enterprise
    agent = await db.agents.find_one()
    if agent:
        print(json.dumps({
            "id": agent.get("id"),
            "tenantId": agent.get("tenantId"),
            "hostname": agent.get("hostname")
        }))
    else:
        print("None")

if __name__ == "__main__":
    asyncio.run(get_agent())
