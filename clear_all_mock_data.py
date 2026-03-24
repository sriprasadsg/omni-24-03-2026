#!/usr/bin/env python3
"""
Clear all old seeded/mock data from the database.
This script clears:
- Old agents (db-prod-01, web-server-03, dev-box-01, sri-server-01)
- Old DAST scans (scan-001)
- Old attack paths
- Old traces and service maps
- Old BI metrics with generated data
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def clear_all_mock_data():
    # Connect to MongoDB
    client = AsyncIOMotorClient("mongodb://127.0.0.1:27017")
    db = client.omni_platform
    
    print("🧹 Clearing All Mock/Seed Data from Database...")
    print("=" * 60)
    
    # 1. Clear old agents
    print("\n1️⃣  Clearing old agents...")
    old_agents = ["db-prod-01", "web-server-03", "dev-box-01", "sri-server-01"]
    for agent_name in old_agents:
        result = await db.agents.delete_many({"agentId": agent_name})
        if result.deleted_count > 0:
            print(f"   ✓ Deleted {result.deleted_count} documents for {agent_name}")
    
    # 2. Clear DAST scans
    print("\n2️⃣  Clearing DAST scans...")
    result = await db.dast_scans.delete_many({})
    print(f"   ✓ Deleted {result.deleted_count} DAST scans")
    
    # 3. Clear chaos experiments
    print("\n3️⃣  Clearing chaos experiments...")
    result = await db.chaos_experiments.delete_many({})
    print(f"   ✓ Deleted {result.deleted_count} chaos experiments")
    
    # 4. Clear attack paths
    print("\n4️⃣  Clearing attack paths...")
    result = await db.attack_paths.delete_many({})
    print(f"   ✓ Deleted {result.deleted_count} attack paths")
    
    # 5. Clear traces
    print("\n5️⃣  Clearing traces...")
    result = await db.traces.delete_many({})
    print(f"   ✓ Deleted {result.deleted_count} traces")
    
    # 6. Clear service maps
    print("\n6️⃣  Clearing service maps...")
    result = await db.service_map.delete_many({})
    print(f"   ✓ Deleted {result.deleted_count} service maps")
    
    # 7. Clear BI metrics
    print("\n7️⃣  Clearing BI metrics with generated data...")
    result = await db.bi_metrics.delete_many({})
    print(f"   ✓ Deleted {result.deleted_count} BI metric entries")
    
    # 8. Count remaining agents
    print("\n📊 Database Status After Cleanup:")
    print("=" * 60)
    agent_count = await db.agents.count_documents({})
    print(f"   Agents remaining: {agent_count}")
    
    if agent_count > 0:
        print("\n   Remaining agents:")
        agents = await db.agents.find({}, {"agentId": 1, "status": 1}).to_list(length=100)
        for agent in agents:
            print(f"      - {agent.get('agentId', 'Unknown')} ({agent.get('status', 'Unknown')})")
    
    print("\n✅ Mock data cleanup complete!")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(clear_all_mock_data())
