import asyncio
from database import get_database, connect_to_mongo, close_mongo_connection

async def reset_super_admin():
    await connect_to_mongo()
    db = get_database()
    result = await db.users.delete_one({"email": "super@omni.ai"})
    print(f"Deleted {result.deleted_count} user(s).")
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(reset_super_admin())
