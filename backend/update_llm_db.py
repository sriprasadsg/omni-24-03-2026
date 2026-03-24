from database import connect_to_mongo, get_database
import asyncio

async def update_llm_model():
    await connect_to_mongo()
    db = get_database()
    
    settings = await db.system_settings.find_one({"type": "llm"})
    if settings:
        current_model = settings.get("model")
        print(f"Current stored model: {current_model}")
        
        # Force update to a known working model if it's the old default or broken
        if current_model == "gemini-pro" or current_model == "gemini-1.5-flash" or not current_model:
            print("Updating model to 'gemini-2.0-flash'...")
            await db.system_settings.update_one(
                {"type": "llm"},
                {"$set": {"model": "gemini-2.0-flash"}}
            )
            print("✅ Model updated in database.")
        else:
            print("Model in DB is already customizable/different. Leaving as is, but ensure it is valid.")
    else:
        print("No LLM settings found to update.")

if __name__ == "__main__":
    asyncio.run(update_llm_model())
