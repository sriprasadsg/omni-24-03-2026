
import asyncio
from database import connect_to_mongo, get_database

async def verify():
    await connect_to_mongo()
    db = get_database()
    
    count = await db.asset_compliance.count_documents({})
    print(f"Compliance Records: {count}")
    
    if count > 0:
        docs = await db.asset_compliance.find({}).to_list(5)
        for doc in docs:
            print(f" - {doc.get('controlId')} ({doc.get('status')})")
            print(f"   Evidence count: {len(doc.get('evidence', []))}")

if __name__ == "__main__":
    asyncio.run(verify())
