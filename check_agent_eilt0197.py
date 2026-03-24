import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone, timedelta
import json

async def check_agent():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["omni_agent_db"]
    
    # Find the EILT0197 agent
    agent = await db.agents.find_one({"hostname": "EILT0197"}, {"_id": 0})
    
    if not agent:
        # Try searching by ID
        agent = await db.agents.find_one({"id": "EILT0197"}, {"_id": 0})
    
    if not agent:
        print("❌ Agent EILT0197 not found in database!")
        print("\nSearching for similar agents...")
        agents = await db.agents.find({}, {"_id": 0, "hostname": 1, "id": 1, "status": 1}).to_list(10)
        for a in agents:
            print(f"  - {a.get('hostname', 'N/A')} (ID: {a.get('id', 'N/A')}): {a.get('status', 'N/A')}")
        return
    
    print("=" * 60)
    print(f"AGENT DATA FOR: {agent.get('hostname', agent.get('id', 'EILT0197'))}")
    print("=" * 60)
    print(json.dumps(agent, indent=2, default=str))
    
    print("\n" + "=" * 60)
    print("TRUST SCORE CALCULATION")
    print("=" * 60)
    
    is_online = agent.get("status") == "Online"
    last_seen = agent.get("lastSeen")
    
    print(f"Status: {agent.get('status', 'Unknown')}")
    print(f"Last Seen: {last_seen}")
    print(f"Is Online: {is_online}")
    
    # Calculate trust factors
    os_patched = is_online
    if last_seen:
        try:
            if isinstance(last_seen, str):
                last_seen_dt = datetime.fromisoformat(last_seen.replace('Z', '+00:00'))
            else:
                last_seen_dt = last_seen
            
            time_since_seen = datetime.now(timezone.utc) - last_seen_dt
            hours_since = time_since_seen.total_seconds() / 3600
            
            print(f"Hours since last seen: {hours_since:.2f}")
            os_patched = time_since_seen < timedelta(hours=24)
            print(f"Seen within 24h: {os_patched}")
        except Exception as e:
            print(f"Error parsing lastSeen: {e}")
            os_patched = is_online
    
    antivirus_active = is_online
    disk_encrypted = True
    compliant_location = True
    
    # Calculate score
    score = 100
    print(f"\nBase Score: {score}")
    
    if not os_patched:
        score -= 30
        print(f"OS Patched Penalty: -30 (Score: {score})")
    else:
        print(f"OS Patched: OK (Score: {score})")
    
    if not antivirus_active:
        score -= 20
        print(f"Antivirus Penalty: -20 (Score: {score})")
    else:
        print(f"Antivirus: OK (Score: {score})")
    
    if not disk_encrypted:
        score -= 20
        print(f"Disk Encrypted Penalty: -20 (Score: {score})")
    else:
        print(f"Disk Encrypted: OK (Score: {score})")
    
    if not compliant_location:
        score -= 30
        print(f"Location Penalty: -30 (Score: {score})")
    else:
        print(f"Compliant Location: OK (Score: {score})")
    
    print(f"\n✓ Final Trust Score: {max(0, score)}%")
    
    print("\n" + "=" * 60)
    print("DIAGNOSIS")
    print("=" * 60)
    
    if not is_online:
        print("⚠️  Agent is OFFLINE - this causes both OS Patched and Antivirus to fail")
        print("    Solution: Agent needs to come online and send heartbeat")
    elif last_seen and time_since_seen >= timedelta(hours=24):
        print("⚠️  Agent hasn't been seen in over 24 hours")
        print(f"    Last seen: {hours_since:.1f} hours ago")
        print("    Solution: Agent needs to send recent heartbeat")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(check_agent())
