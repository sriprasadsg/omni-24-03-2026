from database import connect_to_mongo, close_mongo_connection, get_database
import asyncio

async def main():
    await connect_to_mongo()
    db = get_database()
    devices = await db.network_devices.find({}, {"_id": 0, "hostname": 1, "ipAddress": 1, "tenantId": 1}).to_list(length=100)
    
    print("--- NETWORK DEVICES ---")
    for d in devices:
        print(f"Host: {d.get('hostname')}, IP: {d.get('ipAddress')}, Tenant: {d.get('tenantId')}")
        
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(main())
