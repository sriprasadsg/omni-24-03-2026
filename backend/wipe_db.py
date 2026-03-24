import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient

async def wipe_db():
    print("Initiating full database wipe for 'omni_platform'...")
    client = AsyncIOMotorClient(os.getenv("MONGODB_URI", "mongodb://localhost:27017"))
    db = client.omni_platform
    
    # List of all collections to drop
    collections = await db.list_collection_names()
    
    if not collections:
        print("Database is already empty.")
        return

    for coll in collections:
        print(f"Dropping collection: {coll}")
        await db[coll].drop()

    print("Database wiped successfully. Ready for fresh tenant 'Exafluence'.")

if __name__ == "__main__":
    asyncio.run(wipe_db())
