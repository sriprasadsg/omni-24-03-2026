import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def check():
    client = AsyncIOMotorClient('mongodb://127.0.0.1:27017')
    db = client.omni_platform
    print(f"Checking DB: {db.name}")
    
    cols = await db.list_collection_names()
    print(f"Collections: {cols}")
    
    for col_name in cols:
        count = await db[col_name].count_documents({})
        print(f"  {col_name}: {count}")

if __name__ == "__main__":
    asyncio.run(check())
