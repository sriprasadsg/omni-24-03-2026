import asyncio
import os
from database import get_database, _init_db
from ai_service import IncidentAnalyzer
from motor.motor_asyncio import AsyncIOMotorClient

async def test_ai_service():
    _init_db(AsyncIOMotorClient("mongodb://localhost:27017")["omni_agent_db"])
    analyzer = IncidentAnalyzer()
    await analyzer.initialize()
    print("Is Configured:", analyzer.is_configured)
    print("Active Provider:", analyzer.provider.name if analyzer.provider else "None")
    
    if analyzer.is_configured:
        print("Test Generate:")
        try:
            res = await analyzer.generate_text("Say hello")
            print(res)
        except Exception as e:
            print("Generate Error:", e)

if __name__ == "__main__":
    asyncio.run(test_ai_service())
