import sys
import os
import datetime
import random
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "backend")))

from backend.database import connect_to_mongo, get_database
import asyncio

async def seed_data():
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client['omni_platform']
    
    agent_id = "agent-8d86964b" # Using the ID found
    
    # Generate 50 points over last 24 hours + next 24 hours
    import datetime
    import random
    now = datetime.datetime.utcnow()
    predictions = []
    
    # Generate historical and future data
    # 24 hours history (25 points) + 24 hours forecast (25 points)
    start_time = now - datetime.timedelta(hours=24)
    
    for i in range(50):
        t = start_time + datetime.timedelta(hours=i)
        
        # Simulate some trends
        cpu = 30 + (i % 24) + random.uniform(-5, 5)
        mem = 40 + (i * 0.5) + random.uniform(-2, 2)
        score = 95 - (i * 0.1) # Slowly degrading health for demo
        
        predictions.append({
            "timestamp": t.isoformat() + "Z", # Ensure Z for ISO
            "cpu_prediction": round(cpu, 1),
            "memory_prediction": round(mem, 1),
            "health_score": round(score, 1)
        })

    health_data = {
        "current_score": 92,
        "predictions": predictions,
        "warnings": ["Projected memory increase in 12 hours", "CPU spike predicted"]
    }
    
    # Update Agent
    result = await db.agents.update_one(
        {"id": agent_id},
        {
            "$set": {
                "meta.predictive_health": health_data,
                "status": "Online" # Ensure it's online to show in dashboard
            }
        }
    )
    
    print(f"Updated agent {agent_id}: Matched={result.matched_count}, Modified={result.modified_count}")

if __name__ == "__main__":
    asyncio.run(seed_data())
