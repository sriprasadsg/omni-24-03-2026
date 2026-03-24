from database import connect_to_mongo, close_mongo_connection, get_database
import asyncio
import json

async def main():
    await connect_to_mongo()
    db = get_database()
    
    users = await db.users.find({}, {"_id": 0}).to_list(length=100)
    tenants = await db.tenants.find({}, {"_id": 0}).to_list(length=100)
    
    print("--- USERS ---")
    for u in users:
        print(f"Email: {u.get('email')}, Role: {u.get('role')}, TenantId: {u.get('tenantId')}")
        
    print("\n--- TENANTS ---")
    for t in tenants:
        print(f"Name: {t.get('name')}, ID: {t.get('id')}")
        
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(main())
