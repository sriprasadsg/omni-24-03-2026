from database import connect_to_mongo, mongodb, get_database
import asyncio

async def list_coll():
    await connect_to_mongo()
    # Use the raw database object for listing collections
    raw_db = mongodb.db
    colls = await raw_db.list_collection_names()
    print(f"COLLECTIONS: {colls}")
    
    # Use isolated database for content check
    db = get_database()
    for c in ['system_settings', 'ai_settings', 'llm_settings', 'settings', 'agents']:
        if c in colls:
            docs = await db[c].find({}).to_list(length=10)
            print(f"Content of {c}: {docs}")

if __name__ == "__main__":
    asyncio.run(list_coll())
