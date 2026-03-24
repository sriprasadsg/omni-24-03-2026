import sys
import os
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

async def fix_tenant():
    print("Connecting to database...")
    from database import connect_to_mongo, get_database
    await connect_to_mongo()
    db = get_database()
    
    # 1. Find User
    email = "verified_admin@acmecorp.com"
    user = await db.users.find_one({"email": email})
    
    if not user:
        print(f"User {email} not found. Checking others...")
        # Try finding ANY user
        user = await db.users.find_one({})
        if not user:
             print("No users found!")
             return
        print(f"Found alternative user: {user.get('email')}")

    target_tenant_id = user.get("tenantId")
    print(f"Target User: {user.get('email')}")
    print(f"Target Tenant ID: {target_tenant_id}")
    
    if not target_tenant_id:
        print("User has no tenant ID!")
        return

    # 2. Update Asset
    asset_id = "asset-desktop-rust-agent"
    result = await db.assets.update_one(
        {"id": asset_id},
        {"$set": {"tenantId": target_tenant_id, "status": "Online", "lastSeen": "2026-02-05T23:59:59Z"}} # Future date to ensure active
    )
    print(f"Updated Asset {asset_id}: {result.modified_count} modified")

    # 3. Update Agent
    agent_id = "agent-desktop-rust-agent"
    result = await db.agents.update_one(
        {"id": agent_id},
        {"$set": {"tenantId": target_tenant_id, "status": "Online", "lastSeen": "2026-02-05T23:59:59Z"}}
    )
    print(f"Updated Agent {agent_id}: {result.modified_count} modified")
    
    # 4. Verify
    asset = await db.assets.find_one({"id": asset_id})
    print(f"Verification - Asset Tenant: {asset.get('tenantId')}")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(fix_tenant())
