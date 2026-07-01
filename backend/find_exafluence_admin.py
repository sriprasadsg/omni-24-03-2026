import asyncio
from database import connect_to_mongo, close_mongo_connection, get_database

async def find_exafluence_admin():
    await connect_to_mongo()
    db = get_database()
    # Exafluence tenant ID: tenant_c1344db58834
    user = await db.users.find_one({"tenantId": "tenant_c1344db58834", "role": "Tenant Admin"}, {"_id": 0})
    if user:
        print(f"EXAFLUENCE ADMIN: {user.get('email')}")
    else:
        print("No specific Exafluence admin found.")
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(find_exafluence_admin())
