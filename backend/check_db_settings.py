from database import get_database
import asyncio

async def check_settings():
    from database import connect_to_mongo
    await connect_to_mongo()
    db = get_database()
    settings = await db.system_settings.find_one({"type": "llm"})
    if settings:
        print(f"Provider: {settings.get('provider')}")
        print(f"Model: {settings.get('model')}")
        print(f"API Key start: {settings.get('apiKey')[:5] if settings.get('apiKey') else 'None'}")
    else:
        print("No LLM settings found!")

asyncio.run(check_settings())
