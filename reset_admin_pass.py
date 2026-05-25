"""Reset super admin password to a known value for testing."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

async def main():
    from database import mongodb, connect_to_mongo
    await connect_to_mongo()
    db = mongodb.db

    from auth_utils import hash_password
    new_pass = "Admin@Omni2026!"
    hashed = hash_password(new_pass)

    result = await db.users.update_one(
        {"email": "super@omni.ai"},
        {"$set": {"password": hashed}}
    )
    if result.matched_count:
        print(f"Password reset to: {new_pass}")
    else:
        print("User not found — inserting...")
        import uuid
        from datetime import datetime, timezone
        await db.users.insert_one({
            "id": f"user-{uuid.uuid4()}",
            "tenantId": "platform-admin",
            "tenantName": "Platform",
            "name": "Super Admin",
            "email": "super@omni.ai",
            "password": hashed,
            "role": "Super Admin",
            "status": "Active",
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        print(f"User created with password: {new_pass}")

    await mongodb.close()

asyncio.run(main())
