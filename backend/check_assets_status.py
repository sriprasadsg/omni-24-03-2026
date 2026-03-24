"""
Check current assets in database
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def check_assets():
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017')
    db = client['omni_platform']
    
    print("=" * 60)
    print("AGENTS IN DATABASE:")
    print("=" * 60)
    agents = await db.agents.find({}).to_list(100)
    for agent in agents:
        print(f"\nAgent: {agent.get('hostname', 'NO_HOSTNAME')}")
        print(f"  ID: {agent.get('id', 'NO_ID')}")
        print(f"  AssetID: {agent.get('assetId', 'NO_ASSET_ID')}")
        print(f"  Status: {agent.get('status', 'NO_STATUS')}")
        if 'meta' in agent:
            print(f"  Metrics: CPU={agent['meta'].get('current_cpu')}%, MEM={agent['meta'].get('current_memory')}%, DISK={agent['meta'].get('disk_usage')}%")
    
    print("\n" + "=" * 60)
    print("ASSETS IN DATABASE:")
    print("=" * 60)
    assets = await db.assets.find({}).to_list(100)
    print(f"Total Assets: {len(assets)}\n")
    
    for asset in assets:
        print(f"\nAsset: {asset.get('hostname', 'NO_HOSTNAME')}")
        print(f"  ID: {asset.get('id', 'NO_ID')}")
        print(f"  OS: {asset.get('osName', 'Unknown')}")
        print(f"  IP: {asset.get('ipAddress', 'Unknown')}")
        print(f"  Last Scanned: {asset.get('lastScanned', 'Never')}")
        # Check if it has metrics
        if 'currentMetrics' in asset:
            print(f"  Metrics: {asset.get('currentMetrics')}")
        else:
            print(f"  Metrics: NONE (Asset not being updated with live data)")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(check_assets())
