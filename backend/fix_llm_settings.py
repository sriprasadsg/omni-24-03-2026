from database import get_database, connect_to_mongo
from local_ip import ollama_default_url
import asyncio

async def fix_llm():
    await connect_to_mongo()
    db = get_database()
    
    # Update LLM settings to use Ollama
    await db.system_settings.update_one(
        {"type": "llm"},
        {"$set": {
            "provider": "Ollama (Local)",
            "ollamaUrl": ollama_default_url(),
            "ollamaModel": "llama3.2:3b",
            "model": "llama3.2:3b"
        }},
        upsert=True
    )
    print("Updated LLM settings to Ollama (Local)")

asyncio.run(fix_llm())
