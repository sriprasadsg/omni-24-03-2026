from database import connect_to_mongo, close_mongo_connection, get_database
import asyncio

async def main():
    await connect_to_mongo()
    db = get_database()
    if db:
        nd_count = await db.network_devices.count_documents({})
        as_count = await db.assets.count_documents({})
        devices = await db.network_devices.find({}, {"_id": 0}).to_list(length=5)
        print(f"Network Devices Count: {nd_count}")
        print(f"Assets Count: {as_count}")
        print("Sample Network Devices:")
        for d in devices:
            print(f" - {d.get('hostname')} ({d.get('ipAddress')})")
    else:
        print("Failed to get database instance.")
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(main())
