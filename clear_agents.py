import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def clear_mock_agents():
    """Remove all seeded/mock agents from database"""
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["omni_agent_db"]
    
    print("Removing all mock/seeded agents...")
    result = await db.agents.delete_many({})
    print(f"Removed {result.deleted_count} agents")
    
    # Also clear device_trust_scores if any old mock data exists
    result2 = await db.device_trust_scores.delete_many({})
    if result2.deleted_count > 0:
        print(f"Removed {result2.deleted_count} old device trust scores")
    
    print("\nDatabase cleared - ready for live agents!")
    client.close()

if __name__ == "__main__":
    asyncio.run(clear_mock_agents())
