"""
Check asset with full document details
"""
import asyncio
import json
from motor.motor_asyncio import AsyncIOMotorClient

async def check_asset_detail():
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017')
    db = client['omni_platform']
    
    print("=" * 60)
    print("ASSET DETAIL FOR EILT0197")
    print("=" * 60)
    
    asset = await db.assets.find_one({"hostname": "EILT0197"})
    
    if asset:
        print("\n✅ Asset found!")
        print(f"\nAsset ID: {asset.get('id')}")
        print(f"Hostname: {asset.get('hostname')}")
        print(f"OS: {asset.get('os Name')}")
        print(f"IP: {asset.get('ipAddress')}")
        print(f"Last Scanned: {asset.get('lastScanned')}")
        
        print("\n" + "=" * 60)
        print("CHECKING FOR METRICS FIELD:")
        print("=" * 60)
        
        if 'currentMetrics' in asset:
            print("\n✅ currentMetrics field EXISTS!")
            metrics = asset['currentMetrics']
            print(f"\nCurrent Metrics:")
            print(f"  CPU Usage: {metrics.get('cpuUsage')}%")
            print(f"  Memory Usage: {metrics.get('memoryUsage')}%")
            print(f"  Disk Usage: {metrics.get('diskUsage')}%")
            print(f"  Total Memory: {metrics.get('totalMemoryGB')} GB")
            print(f"  Available Memory: {metrics.get('availableMemoryGB')} GB")
            print(f"  Disk Total: {metrics.get('diskTotalGB')} GB")
            print(f"  Disk Used: {metrics.get('diskUsedGB')} GB")
            print(f"  Collected At: {metrics.get('collectedAt')}")
        else:
            print("\n❌ currentMetrics field DOES NOT EXIST")
            print("\nAvailable fields in asset:")
            for key in asset.keys():
                if key != '_id':
                    print(f"  - {key}")
        
        print("\n" + "=" * 60)
        print("FULL ASSET DOCUMENT:")
        print("=" * 60)
        # Pretty print the full document
        asset_copy = dict(asset)
        if '_id' in asset_copy:
            asset_copy['_id'] = str(asset_copy['_id'])
        print(json.dumps(asset_copy, indent=2))
        
    else:
        print("\n❌ Asset NOT found for hostname EILT0197")
        print("\nAll assets in database:")
        assets = await db.assets.find({}).to_list(100)
        for a in assets:
            print(f"  - {a.get('hostname', 'NO_HOSTNAME')} (id: {a.get('id', 'NO_ID')})")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(check_asset_detail())
