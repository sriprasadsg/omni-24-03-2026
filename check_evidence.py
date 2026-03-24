import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def check_evidence():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["omni_platform"]
    
    count = await db.asset_compliance.count_documents({})
    print(f"Total Asset Compliance Records: {count}")
    
    cursor = db.asset_compliance.find({}).limit(5)
    async for doc in cursor:
        print(f"Asset: {doc.get('assetId')}, Control: {doc.get('controlId')}, Status: {doc.get('status')}")
        if 'evidence' in doc:
            print(f"  Evidence Count: {len(doc['evidence'])}")

if __name__ == "__main__":
    asyncio.run(check_evidence())
