
import asyncio
from database import connect_to_mongo, get_database, close_mongo_connection

async def check():
    await connect_to_mongo()
    db = get_database()
    count = await db.network_devices.count_documents({})
    print(f"Network Devices Count: {count}")
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(check())
