
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def check_fields():
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017')
    db = client['omni_platform']
    asset = await db.assets.find_one({'hostname': 'EILT0197'})
    if asset:
        fields = ['osEdition', 'osDisplayVersion', 'osInstalledOn', 'osBuild', 'osExperience', 'serialNumber', 'osName', 'osVersion']
        for f in fields:
            print(f"{f}: {asset.get(f)}")
    else:
        print("Asset not found")
    client.close()

if __name__ == "__main__":
    asyncio.run(check_fields())
