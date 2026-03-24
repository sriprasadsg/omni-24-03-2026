
import asyncio
from database import connect_to_mongo, close_mongo_connection, get_database

async def scan():
    print("--- Scanning Compliance Docs ---")
    await connect_to_mongo()
    db = get_database()
    
    docs = await db.asset_compliance.find({}).to_list(length=5)
    
    with open("scan_out.txt", "w", encoding="utf-8") as f:
        for d in docs:
            # Convert ObjectId to str
            d['_id'] = str(d.get('_id'))
            f.write(str(d) + "\n\n")

    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(scan())
