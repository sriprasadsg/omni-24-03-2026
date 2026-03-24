from database import get_database, connect_to_mongo
import asyncio

async def fix_llm():
    await connect_to_mongo()
    db = get_database()
    
    # Update LLM settings to exactly what ai_service.py expects ("Ollama (Local)")
    await db.system_settings.update_one(
        {"type": "llm"},
        {"$set": {
            "provider": "Ollama (Local)",
            "ollamaUrl": "http://localhost:11434",
            "ollamaModel": "llama3.2:3b",
            "model": "llama3.2:3b"
        }},
        upsert=True
    )
    print("Updated LLM settings to precisely match 'Ollama (Local)'")

asyncio.run(fix_llm())
