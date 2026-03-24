#!/usr/bin/env python3
"""
Manual cleanup script to remove old seeded agents by their specific database IDs.
This is needed because the automated cleanup script couldn't identify them.
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def manual_cleanup():
    # Connect to MongoDB
    client = AsyncIOMotorClient("mongodb://127.0.0.1:27017")
    db = client.omni_platform
    
    print("🗑️  Manual Cleanup: Removing Old Seeded Agents")
    print("=" * 60)
    
    # Method 1: Delete by internal MongoDB _id (if known)
    old_internal_ids = ["agent-1", "agent-2", "agent-3", "agent-sri-1"]
    
    print("\n📋 Attempting to delete by internal IDs...")
    result1 = await db.agents.delete_many({"_id": {"$in": old_internal_ids}})
    print(f"   Deleted {result1.deleted_count} agents by _id")
    
    # Method 2: Delete by agentId field
    old_agent_names = ["db-prod-01", "web-server-03", "dev-box-01", "sri-server-01"]
    
    print("\n📋 Attempting to delete by agentId field...")
    result2 = await db.agents.delete_many({"agentId": {"$in": old_agent_names}})
    print(f"   Deleted {result2.deleted_count} agents by agentId")
    
    # Method 3: Delete all agents with lastSeen before a certain time
    # (old seeded data has timestamp 2/16/2026, 2:29:12 PM)
    from datetime import datetime, timezone
    cutoff_time = datetime(2026, 2, 16, 14, 30, 0, tzinfo=timezone.utc).isoformat()
    
    print(f"\n📋 Attempting to delete by timestamp (before {cutoff_time})...")
    result3 = await db.agents.delete_many({"lastSeen": {"$lt": cutoff_time}})
    print(f"   Deleted {result3.deleted_count} agents by timestamp")
    
    # Check remaining agents
    print("\n📊 Database Status After Manual Cleanup:")
    print("=" * 60)
    remaining = await db.agents.count_documents({})
    print(f"   Agents remaining: {remaining}")
    
    if remaining > 0:
        print("\n   Remaining agents:")
        agents = await db.agents.find({}, {"agentId": 1, "status": 1, "lastSeen": 1}).to_list(length=100)
        for agent in agents:
            print(f"      - {agent.get('agentId', 'NO_ID')} ({agent.get('status', 'NO_STATUS')}) - lastSeen: {agent.get('lastSeen', 'NEVER')}")
    
    print("\n✅ Manual cleanup complete!")
    print("\n💡 Tip: Restart backend and live agent daemon to register new agents:")
    print("   python backend/app.py")
    print("   python backend/live_agent_daemon.py")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(manual_cleanup())
