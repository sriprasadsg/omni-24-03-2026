import asyncio, bcrypt, os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
load_dotenv()

async def check():
    url = os.getenv("MONGODB_URL", "mongodb://127.0.0.1:27017").strip()
    dbname = os.getenv("MONGODB_DB_NAME", "omni_platform")
    c = AsyncIOMotorClient(url)
    db = c[dbname]

    # Find ALL users with this email (no filter — duplicates possible)
    cursor = db.users.find({"email": "super@omni.ai"})
    users = await cursor.to_list(length=100)
    print(f"Total records with email super@omni.ai: {len(users)}")
    for i, user in enumerate(users):
        pw_hash = user.get("password", "")
        print(f"\n--- Record {i+1} ---")
        print("  _id     :", user.get("_id"))
        print("  tenantId:", user.get("tenantId"))
        print("  role    :", user.get("role"))
        print("  status  :", user.get("status"))
        print("  pw hash :", pw_hash[:50], "...")
        for pwd in ["Admin@2030!", "Admin@1234", "admin123", "password123"]:
            try:
                ok = bcrypt.checkpw(pwd.encode(), pw_hash.encode())
            except Exception as e:
                ok = f"ERROR: {e}"
            if ok is True:
                print(f"  >>> PASSWORD MATCH: {pwd!r}")
    c.close()

asyncio.run(check())
