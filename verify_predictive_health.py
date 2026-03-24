import sys
import os
import requests
import json
sys.path.append(os.path.abspath("backend"))

# Assuming backend is running on 5000
API_URL = "http://localhost:5000/api/agents"

def verify():
    # Login first? No, list agents might be protected or I need a token.
    # Actually, getting agent details usually requires auth.
    # Let's try to fetch the specific agent from DB directly for verification
    # to avoid auth complexity in script, similar to how I seeded it.
    
    from backend.database import connect_to_mongo, get_database
    import asyncio

    async def check_db():
        await connect_to_mongo()
        db = get_database()
        agent = await db.agents.find_one({"id": "agent-EILT0197"})
        
        if not agent:
            print("❌ Agent not found")
            return
            
        ph = agent.get("meta", {}).get("predictive_health", {})
        predictions = ph.get("predictions", [])
        
        print(f"Agent: {agent.get('hostname')}")
        print(f"Current Health Score: {ph.get('current_score')}")
        print(f"Predictions count: {len(predictions)}")
        print(f"Warnings: {ph.get('warnings')}")
        
        if len(predictions) >= 50:
            print("✅ Data requirements met (>= 50 samples)")
        else:
            print("❌ Insufficient samples")

    asyncio.run(check_db())

if __name__ == "__main__":
    verify()
