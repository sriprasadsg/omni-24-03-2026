import sys
import os
sys.path.insert(0, os.path.join(os.getcwd(), 'backend'))
from database import get_database, connect_to_mongo
import asyncio

async def main():
    await connect_to_mongo()
    db = get_database()
    # Check for EILT0197 or asset-EILT0197
    # Find latest update time
    cursor = db.asset_compliance.find({"assetId": "asset-EILT0197"}).sort("lastUpdated", -1).limit(1)
    async for doc in cursor:
        print(f"Latest Compliance Update: {doc.get('lastUpdated')}")

if __name__ == "__main__":
    asyncio.run(main())
