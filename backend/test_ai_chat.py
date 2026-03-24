import asyncio
import json
from ai_service import ai_service
from database import connect_to_mongo

async def test_ai():
    await connect_to_mongo()
    # Mock context
    context = {"currentView": "dashboard"}
    try:
        response = await ai_service.chat("Who are you?", context)
        print(f"AI Response: {response}")
    except Exception as e:
        print(f"AI Error: {e}")

asyncio.run(test_ai())
