import httpx
import asyncio

async def test():
    async with httpx.AsyncClient() as client:
        # Get assets
        resp = await client.get('http://localhost:5000/api/assets')
        assets = resp.json()
        
        if not assets:
            print("No assets found!")
            return
            
        asset = assets[0]
        asset_id = asset['id']
        hostname = asset['hostname']
        
        print(f"Testing metrics for: {hostname} (ID: {asset_id})")
        print(f"RAM: {asset.get('ram')}")
        print(f"CPU: {asset.get('cpuModel')}\n")
        
        # Get metrics for this asset
        metrics_resp = await client.get(f'http://localhost:5000/api/assets/{asset_id}/metrics?range=24h')
        metrics = metrics_resp.json()
        
        print(f"Metrics data points: {len(metrics)}")
        if metrics:
            print("\nLatest 3 data points:")
            for m in metrics[-3:]:
                print(f"  Time: {m.get('timestamp')}")
                print(f"    CPU: {m.get('cpu')}%, MEM: {m.get('memory')}%, DISK: {m.get('disk')}%")
                print(f"    Network: {m.get('network')} MB")
        else:
            print("No metrics data!")

if __name__ == "__main__":
    asyncio.run(test())
