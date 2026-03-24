import asyncio
from database import connect_to_mongo, get_database

async def check():
    await connect_to_mongo()
    db = get_database()
    
    # Check for agents
    agents = await db.agents.find().to_list(10)
    print(f"Agents: {len(agents)}")
    if agents:
        for a in agents:
            print(f"  - {a.get('hostname')} (ID: {a.get('id')})")
    
    # Check for assets
    assets = await db.assets.find().to_list(10)
    print(f"\nAssets: {len(assets)}")
    if assets:
        for a in assets:
            print(f"  - {a.get('hostname')} (ID: {a.get('id')})")
            print(f"    RAM: {a.get('ram')}, CPU: {a.get('cpuModel')}")
    
    # Check for metrics
    metrics = await db.asset_metrics.find().sort("timestamp", -1).to_list(5)
    print(f"\nMetrics: {len(metrics)}")
    if metrics:
        for m in metrics:
            print(f"  - Asset: {m.get('assetId')}, Time: {m.get('timestamp')}")
            print(f"    CPU: {m.get('cpu')}%, MEM: {m.get('memory')}%")

if __name__ == "__main__":
    asyncio.run(check())
