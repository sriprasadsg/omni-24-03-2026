import requests
import json
import sys

BASE_URL = "http://localhost:5000/api"

def simulate_frontend():
    print("1. Logging in...")
    try:
        resp = requests.post(f"{BASE_URL}/auth/login", json={"email": "admin@example.com", "password": "admin123"})
    except Exception as e:
        print(f"Login failed: {e}")
        # Try without auth or different creds if needed, acts as "admin"
        return

    if resp.status_code != 200:
        print(f"Login failed: {resp.status_code} {resp.text}")
        return

    token = resp.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}
    print("✅ Login successful")

    print("\n2. Fetching Agents to find EILT0197...")
    resp = requests.get(f"{BASE_URL}/agents", headers=headers)
    if resp.status_code != 200:
        print(f"❌ Failed to fetch agents: {resp.status_code}")
        return
    
    agents = resp.json()
    if isinstance(agents, dict) and "items" in agents:
        agents = agents["items"]
        
    target_agent = next((a for a in agents if a.get("hostname") == "EILT0197"), None)
    
    if not target_agent:
        print("❌ Agent EILT0197 not found in list")
        # List what is there
        print("Available agents:", [a.get("hostname") for a in agents])
        return

    print(f"✅ Found Agent: {target_agent.get('hostname')}")
    print(f"   ID: {target_agent.get('id')}")
    print(f"   Asset ID: {target_agent.get('assetId')}")
    
    # Check Predictive Health Data in Agent Meta (Frontend uses this directly)
    ph_data = target_agent.get('meta', {}).get('predictive_health')
    print("\n3. Checking Predictive Health Data (from Agent Meta)...")
    if ph_data:
        print("✅ Data present in meta")
        print(json.dumps(ph_data, indent=2)[:200] + "...") 
    else:
        print("❌ Predictive Health data MISSING in agent meta")

    # Check Compliance Data (Frontend calls endpoint)
    asset_id = target_agent.get('assetId')
    if not asset_id:
        print("❌ No Asset ID linked, cannot fetch compliance")
        return

    print(f"\n4. Fetching Compliance for Asset {asset_id}...")
    resp = requests.get(f"{BASE_URL}/assets/{asset_id}/compliance", headers=headers)
    
    if resp.status_code == 200:
        data = resp.json()
        print(f"✅ Compliance API returned {len(data)} items")
        if len(data) > 0:
            print(json.dumps(data[0], indent=2))
        else:
            print("⚠️ Compliance data is empty list")
    else:
        print(f"❌ Compliance API failed: {resp.status_code}")

    print("\n5. Fetching ALL Compliance Evidence (Debug)...")
    resp = requests.get(f"{BASE_URL}/compliance/evidence", headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        print(f"✅ Global Evidence API returned {len(data)} items")
        if len(data) > 0:
             # Check if our asset is in there
             found = [d for d in data if d.get('assetId') == asset_id]
             print(f"   Items for {asset_id}: {len(found)}")
             if len(found) > 0:
                 print("   Sample:", json.dumps(found[0], indent=2))
    else:
        print(f"❌ Global Evidence API failed: {resp.status_code}")

if __name__ == "__main__":
    simulate_frontend()
