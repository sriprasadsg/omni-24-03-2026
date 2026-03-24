from dotenv import load_dotenv
load_dotenv()
import asyncio
from database import connect_to_mongo, get_database

async def clear_assets():
    await connect_to_mongo()
    db = get_database()
    result = await db.assets.delete_many({})
    print(f"Deleted {result.deleted_count} assets.")

if __name__ == "__main__":
    asyncio.run(clear_assets())
