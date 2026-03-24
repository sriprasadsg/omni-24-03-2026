import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def get_llm():
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client.omni_agent_db
    doc = await db.system_settings.find_one({'type': 'llm'})
    print(f"DB DOC: {doc}")

asyncio.run(get_llm())
