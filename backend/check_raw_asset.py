
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import json

async def check_raw_asset():
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017')
    db = client['omni_platform']
    asset = await db.assets.find_one({'hostname': 'EILT0197'})
    if asset:
        # Convert ObjectId to string for JSON serialization
        if '_id' in asset:
            asset['_id'] = str(asset['_id'])
        print(json.dumps(asset, indent=2))
    else:
        print("Asset not found")
    client.close()

if __name__ == "__main__":
    asyncio.run(check_raw_asset())
