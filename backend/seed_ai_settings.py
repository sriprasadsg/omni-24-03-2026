
import asyncio
from database import get_database, connect_to_mongo

async def seed_ai_settings():
    print("Connecting to database...")
    await connect_to_mongo()
    db = get_database()
    
    settings = {
        "type": "llm",
        "provider": "ollama",
        "model": "llama3.2:3b",
        "ollamaUrl": "http://localhost:11434",
        "ollamaModel": "llama3.2:3b"
    }
    
    print("Updating AI settings in system_settings collection...")
    # NOTE: db is TenantIsolatedDatabase wrapper. It acts like a dict/attr access.
    # But it wraps collections. system_settings is a collection.
    
    result = await db.system_settings.update_one(
        {"type": "llm"},
        {"$set": settings},
        upsert=True
    )
    
    print(f"Update acknowledged: {result.acknowledged}")
    print(f"Matched count: {result.matched_count}")
    print(f"Modified count: {result.modified_count}")
    print("AI Settings successfully seeded.")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(seed_ai_settings())
