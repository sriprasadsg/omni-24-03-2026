from database import get_database
import asyncio

async def check():
    db = get_database()
    count = await db.agent_metrics.count_documents({})
    print(f"Total metrics in agent_metrics: {count}")
    
    recent = await db.agent_metrics.find().sort("timestamp", -1).limit(5).to_list(length=5)
    for m in recent:
        print(f"Metric: {m.get('agent_id')} at {m.get('timestamp')} - CPU: {m.get('cpu_percent')}%")

if __name__ == "__main__":
    asyncio.run(check())
