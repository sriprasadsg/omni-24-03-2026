import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from compliance_service import evaluate_asset_compliance
import os

# Mock the get_database function used in compliance_service by monkeypatching or just setting up the context if possible
# But compliance_service imports get_database from somewhere. 
# Let's just modify the import in compliance_service or manually replicate the logic here to see what's wrong.

# Actually, let's just use the app's db connection if we can import it, or just reproduce the find logic.
# Better: Let's simply call the `evaluate_asset_compliance` function if we can set up the DB it expects.
# It calls `get_database()`. Let's see where `get_database` comes from. 
# It likely comes from `app` or a utils file. 

# Let's inspect compliance_service.py imports first to be sure how to run it.
# ... I'll blindly try to run a script that connects to DB and prints the asset first.

async def debug():
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client.agent_platform
    
    # 1. Get an asset
    asset = await db.assets.find_one({})
    if not asset:
        print("No assets found in DB!")
        return
        
    print(f"Found Asset: {asset.get('hostname')} (ID: {asset.get('id')})")
    print(f"Asset AgentId: {asset.get('agentId')}")
    print("Software count:", len(asset.get('installedSoftware', [])))
    
    # 2. Try the logic manually
    from compliance_service import evaluate_asset_compliance
    from app import get_database # Try importing, might fail if app init has side effects
    
    # Actually, compliance_service does `db = get_database()`. 
    # If I can't easily mock that, I'll just write a request to the running API.
    
    import aiohttp
    async with aiohttp.ClientSession() as session:
        url = f"http://localhost:5000/api/assets/{asset.get('id')}/compliance"
        print(f"Fetching {url}...")
        async with session.get(url) as resp:
            print(f"Status: {resp.status}")
            if resp.status == 200:
                data = await resp.json()
                print("Compliance Report:", data)
            else:
                print("Error:", await resp.text())
                
                # Check metrics endpoint too
                url_metrics = f"http://localhost:5000/api/assets/{asset.get('id')}/metrics"
                async with session.get(url_metrics) as resp2:
                     print(f"Metrics Status: {resp2.status}")

if __name__ == "__main__":
    asyncio.run(debug())
