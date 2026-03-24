from database import get_database, connect_to_mongo
import asyncio

async def check():
    await connect_to_mongo()
    database_wrapper = get_database()
    if not database_wrapper:
        print("Failed to get database wrapper")
        return
        
    # Bypass tenant isolation for debugging
    raw_db = database_wrapper._db
    
    count = await raw_db.agent_metrics.count_documents({})
    print(f"Total metrics in agent_metrics (raw): {count}")
    
    recent = await raw_db.agent_metrics.find().sort("timestamp", -1).limit(5).to_list(length=5)
    for m in recent:
        print(f"Metric: {m.get('agent_id')} at {m.get('timestamp')} - CPU: {m.get('cpu_percent')}%")

    asset_count = await raw_db.asset_metrics.count_documents({})
    print(f"Total metrics in asset_metrics (raw): {asset_count}")

if __name__ == "__main__":
    asyncio.run(check())
