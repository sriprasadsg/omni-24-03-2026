"""
Direct super-admin password reset — bypasses tenant isolation wrapper.
Run from backend/ directory:
  venv\\Scripts\\python.exe fix_super_admin.py
"""
import asyncio
import os
import uuid
import bcrypt
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://127.0.0.1:27017").strip()
DB_NAME = os.getenv("MONGODB_DB_NAME", "omni_platform")
NEW_PASSWORD = "Admin@2030!"


def hash_pw(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


async def main():
    client = AsyncIOMotorClient(MONGODB_URL, serverSelectionTimeoutMS=5000)
    await client.server_info()
    col = client[DB_NAME]["users"]

    user = await col.find_one({"email": "super@omni.ai"})
    new_hash = hash_pw(NEW_PASSWORD)

    if user:
        await col.update_one(
            {"email": "super@omni.ai"},
            {"$set": {"password": new_hash, "status": "Active", "role": "Super Admin"}}
        )
        print(f"[OK] Password reset for existing user (tenantId={user.get('tenantId')})")
    else:
        doc = {
            "id": f"user-{uuid.uuid4()}",
            "tenantId": "platform-admin",
            "tenantName": "Platform",
            "name": "Super Admin",
            "email": "super@omni.ai",
            "password": new_hash,
            "role": "Super Admin",
            "status": "Active",
        }
        await col.insert_one(doc)
        print("[OK] Super admin user created from scratch")

    # Verify
    updated = await col.find_one({"email": "super@omni.ai"})
    ok = bcrypt.checkpw(NEW_PASSWORD.encode(), updated["password"].encode())
    print(f"[OK] Verification: password hash matches = {ok}")
    print(f"     tenantId = {updated.get('tenantId')}")
    print(f"\nLogin with:  super@omni.ai  /  {NEW_PASSWORD}")
    client.close()


asyncio.run(main())
