import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone, timedelta
import json

async def search_agent():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["omni_agent_db"]
    
    search_term = "EILT0197"
    
    print(f"Searching for: {search_term}")
    print("=" * 60)
    
    # Search in multiple fields
    agent = await db.agents.find_one({
        "$or": [
            {"hostname": search_term},
            {"id": search_term},
            {"assetId": search_term},
            {"meta.assetId": search_term},
        ]
    }, {"_id": 0})
    
    if not agent:
        print(f"❌ No agent found with {search_term} in common fields")
        print("\nListing all agents to identify the pattern...")
        agents = await db.agents.find({}, {"_id": 0}).to_list(20)
        
        print(f"\nFound {len(agents)} agents:")
        for i, a in enumerate(agents[:10], 1):
            hostname = a.get('hostname', 'N/A')
            asset_id = a.get('assetId') or a.get('meta', {}).get('assetId', 'N/A')
            status = a.get('status', 'N/A')
            last_seen = a.get('lastSeen', 'N/A')
            print(f"{i}. Hostname: {hostname}")
            print(f"   AssetID: {asset_id}")
            print(f"   Status: {status}")
            print(f"   Last Seen: {last_seen}")
            print()
        
        if len(agents) > 10:
            print(f"... and {len(agents) - 10} more")
        
        client.close()
        return
    
    # Agent found - analyze it
    print(f"✓ Found agent!")
    print("\n" + "=" * 60)
    print("FULL AGENT DATA")
    print("=" * 60)
    print(json.dumps(agent, indent=2, default=str))
    
    # Analyze trust score
    print("\n" + "=" * 60)
    print("TRUST SCORE ANALYSIS")
    print("=" * 60)
    
    is_online = agent.get("status") == "Online"
    last_seen = agent.get("lastSeen")
    
    print(f"Hostname: {agent.get('hostname', 'N/A')}")
    print(f"AssetID: {agent.get('assetId') or agent.get('meta', {}).get('assetId', 'N/A')}")
    print(f"Status: {agent.get('status', 'Unknown')}")
    print(f"Last Seen: {last_seen}")
    print(f"Is Online: {is_online}")
    
    # Calculate trust factors (matching backend logic)
    os_patched = is_online
    if last_seen:
        try:
            if isinstance(last_seen, str):
                last_seen_dt = datetime.fromisoformat(last_seen.replace('Z', '+00:00'))
            else:
                last_seen_dt = last_seen
            
            time_since_seen = datetime.now(timezone.utc) - last_seen_dt
            hours_since = time_since_seen.total_seconds() / 3600
            
            print(f"\nTime since last seen: {hours_since:.2f} hours")
            os_patched = time_since_seen < timedelta(hours=24)
        except Exception as e:
            print(f"Error parsing lastSeen: {e}")
    
    antivirus_active = is_online
    disk_encrypted = True
    compliant_location = True
    
    # Calculate score
    score = 100
    print(f"\nTrust Score Calculation:")
    print(f"  Base: {score}%")
    
    if not os_patched:
        score -= 30
        print(f"  - OS Patched: ✗ (-30%) = {score}%")
    else:
        print(f"  - OS Patched: ✓ = {score}%")
    
    if not antivirus_active:
        score -= 20
        print(f"  - Antivirus: ✗ (-20%) = {score}%")
    else:
        print(f"  - Antivirus: ✓ = {score}%")
    
    if not disk_encrypted:
        score -= 20
        print(f"  - Encrypted: ✗ (-20%) = {score}%")
    else:
        print(f"  - Encrypted: ✓ = {score}%")
    
    if not compliant_location:
        score -= 30
        print(f"  - Location: ✗ (-30%) = {score}%")
    else:
        print(f"  - Location: ✓ = {score}%")
    
    print(f"\n✓ Final Score: {max(0, score)}%")
    
    # Diagnosis
    print("\n" + "=" * 60)
    print("DIAGNOSIS & FIX")
    print("=" * 60)
    
    if not is_online:
        print("⚠️  Issue: Agent status is OFFLINE")
        print("   This causes:")
        print("   - OS Patched check to fail (-30%)")
        print("   - Antivirus check to fail (-20%)")
        print("\n   Fix: Update agent status to 'Online' or ensure agent sends heartbeat")
    elif last_seen and time_since_seen >= timedelta(hours=24):
        print(f"⚠️  Issue: Agent last seen {hours_since:.1f} hours ago (>24h threshold)")
        print("   This causes OS Patched check to fail (-30%)")
        print("\n   Fix: Update lastSeen timestamp or ensure agent sends recent heartbeat")
    else:
        print("✓ Agent appears healthy - scores match expected behavior")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(search_agent())
