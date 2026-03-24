import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import json

async def check_all_sources():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["omni_agent_db"]
    
    print("=" * 70)
    print("CHECKING ALL ZERO TRUST DATA SOURCES")
    print("=" * 70)
    
    # Check agents collection
    print("\n1. AGENTS COLLECTION:")
    print("-" * 70)
    agents = await db.agents.find({}, {"_id": 0}).to_list(100)
    print(f"   Total agents: {len(agents)}")
    if agents:
        for i, agent in enumerate(agents[:5], 1):
            hostname = agent.get('hostname', 'N/A')
            status = agent.get('status', 'N/A')
            asset_id = agent.get('assetId') or agent.get('meta', {}).get('assetId', 'N/A')
            print(f"   {i}. {hostname} | AssetID: {asset_id} | Status: {status}")
        if len(agents) > 5:
            print(f"   ... and {len(agents) - 5} more")
    else:
        print("   ⚠️  No agents found!")
    
    # Check device_trust_scores collection (old mock data source)
    print("\n2. DEVICE_TRUST_SCORES COLLECTION (old mock data):")
    print("-" * 70)
    devices = await db.device_trust_scores.find({}, {"_id": 0}).to_list(100)
    print(f"   Total devices: {len(devices)}")
    if devices:
        print("   ⚠️  Found old mock data!")
        for i, device in enumerate(devices[:10], 1):
            device_id = device.get('deviceId', 'N/A')
            score = device.get('score', 'N/A')
            factors = device.get('factors', {})
            print(f"   {i}. {device_id}: {score}% | OS:{factors.get('osPatched')} AV:{factors.get('antivirusActive')}")
        if len(devices) > 10:
            print(f"   ... and {len(devices) - 10} more")
        
        # Check if EILT0197 is in this collection
        eilt_device = await db.device_trust_scores.find_one({"deviceId": "EILT0197"}, {"_id": 0})
        if eilt_device:
            print("\n   ✓ FOUND EILT0197 in device_trust_scores:")
            print(json.dumps(eilt_device, indent=6, default=str))
    else:
        print("   ✓ No old mock data (as expected)")
    
    # Check user_sessions collection
    print("\n3. USER_SESSIONS COLLECTION:")
    print("-" * 70)
    sessions = await db.user_sessions.find({}, {"_id": 0}).to_list(100)
    print(f"   Total sessions: {len(sessions)}")
    if sessions:
        for i, session in enumerate(sessions[:5], 1):
            session_id = session.get('sessionId', 'N/A')
            user_id = session.get('userId', 'N/A')
            risk = session.get('riskScore', 'N/A')
            print(f"   {i}. {session_id} | User: {user_id} | Risk: {risk}")
    else:
        print("   ✓ No sessions (as expected after cleanup)")
    
    print("\n" + "=" * 70)
    print("DIAGNOSIS")
    print("=" * 70)
    
    if len(agents) == 0 and len(devices) > 0:
        print("⚠️  PROBLEM IDENTIFIED:")
        print("   - No agents in 'agents' collection")
        print("   - Old mock data still in 'device_trust_scores' collection")
        print("   - API endpoint may still be reading from old collection!")
        print("\n   ROOT CAUSE:")
        print("   - Backend restart may not have loaded updated code")
        print("   - OR endpoint is still using old collection")
        print("\n   FIX:")
        print("   1. Verify backend code is using agents collection")
        print("   2. Restart backend service")
        print("   3. Clear device_trust_scores collection (optional)")
        print("   4. Register test agents")
    elif len(agents) == 0:
        print("⚠️  NO AGENT DATA:")
        print("   - Need to register agents first")
        print("\n   FIX:")
        print("   - Run: python backend/simulate_agent_activity.py")
    else:
        print("✓ Data looks correct - agents collection has data")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(check_all_sources())
