import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from local_ip import ollama_default_url

async def set_ollama():
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client.omni_agent_db
    result = await db.system_settings.update_one(
        {'type': 'llm'},
        {'$set': {
            'provider': 'Ollama (Local)',
            'ollamaUrl': ollama_default_url(),
            'ollamaModel': 'llama3.2:3b'
        }},
        upsert=True
    )
    print(f"Updated LLM settings to use Ollama. Matched: {result.matched_count}, Modified: {result.modified_count}, Upserted ID: {result.upserted_id}")
    
asyncio.run(set_ollama())
