import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def check_dupes():
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client.omni_platform
    
    count = await db.asset_compliance.count_documents({})
    print('Total asset_compliance:', count)
    
    pipeline = [
        {'$group': {
            '_id': {'assetId': '$assetId', 'controlId': '$controlId', 'frameworkId': '$frameworkId'}, 
            'count': {'$sum': 1}
        }}, 
        {'$match': {'count': {'$gt': 1}}}
    ]
    
    dupes = await db.asset_compliance.aggregate(pipeline).to_list(length=100)
    print('Dupes by composite key:', len(dupes))
    if dupes:
        print("First dupe:", dupes[0])
        
    cursor = db.asset_compliance.find({}).limit(1)
    async for doc in cursor:
        print("Evidence array length for a doc:", len(doc.get("evidence", [])))

if __name__ == "__main__":
    asyncio.run(check_dupes())
