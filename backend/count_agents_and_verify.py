from database import get_database, connect_to_mongo
import asyncio

async def count_agents():
    await connect_to_mongo()
    db = get_database()
    
    count = await db.agents.count_documents({})
    print(f"Total Agents: {count}")
    
    # Also check LLM settings again
    settings = await db.system_settings.find_one({"type": "llm"})
    print(f"Current LLM Provider: {settings.get('provider') if settings else 'None'}")

asyncio.run(count_agents())
