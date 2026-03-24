from database import connect_to_mongo, get_database
import asyncio
import os

async def check_settings():
    await connect_to_mongo()
    db = get_database()
    settings = await db.system_settings.find_one({"type": "llm"})
    print(f"LLM Settings: {settings}")
    
    # Also check ai_settings
    ai_settings = await db.ai_settings.find_one({"tenant_id": "global"})
    print(f"AI Settings: {ai_settings}")
    
    # Check agents
    agent = await db.agents.find_one({})
    if agent:
        print(f"Found sample agent: {agent['id']}")
    else:
        print("No agents found in DB.")

if __name__ == "__main__":
    asyncio.run(check_settings())
