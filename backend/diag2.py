import asyncio, bcrypt, os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
load_dotenv()

NEW_PASSWORD = "Admin@2030"

async def main():
    c = AsyncIOMotorClient(os.getenv("MONGODB_URL", "mongodb://127.0.0.1:27017").strip())
    db = c[os.getenv("MONGODB_DB_NAME", "omni_platform")]
    col = db["users"]

    new_hash = bcrypt.hashpw(NEW_PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    print("New hash:", new_hash)

    r = await col.update_one(
        {"email": "super@omni.ai"},
        {"$set": {"password": new_hash}}
    )
    print("Matched:", r.matched_count, "Modified:", r.modified_count)

    user = await col.find_one({"email": "super@omni.ai"})
    stored = user["password"]
    print("Stored hash:", stored)
    print("Same hash?", stored == new_hash)

    ok = bcrypt.checkpw(NEW_PASSWORD.encode("utf-8"), stored.encode("utf-8"))
    print("checkpw result:", ok)
    c.close()

asyncio.run(main())
