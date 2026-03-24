import requests
import json
import time

BASE_URL = "http://localhost:5000/api"

def run_verification():
    print("=== Starting Move Agent Verification ===")
    
    # 1. Login as Platform Admin (since moving agents might be restricted)
    print("1. Authenticating as Platform Admin...")
    payload = {"email": "testadmin@example.com", "password": "password123"}
    resp = requests.post(f"{BASE_URL}/auth/login", json=payload)
    
    if resp.status_code != 200:
        print(f"❌ Login failed: {resp.text}")
        return
        
    token = resp.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}
    print("✅ Authenticated.")
    
    # 2. Get an Agent
    print("\n2. Fetching Agents...")
    resp = requests.get(f"{BASE_URL}/agents", headers=headers)
    agents = resp.json().get("items", [])
    
    if not agents:
        print("❌ No agents found to move.")
        return
        
    target_agent = agents[0]
    original_tenant = target_agent.get("tenant_id")
    agent_id = target_agent.get("id")
    
    print(f"   Selected Agent: {target_agent.get('hostname')} ({agent_id})")
    print(f"   Current Tenant: {original_tenant}")
    
    # 3. Get Tenants (to find a target)
    print("\n3. Fetching Tenants...")
    resp = requests.get(f"{BASE_URL}/tenants", headers=headers)
    tenants = resp.json()
    
    if len(tenants) < 2:
        print("⚠️ Not enough tenants to test move. Need at least 2.")
        # Attempt to create a dummy tenant?
        return
        
    # Find a different tenant
    target_tenant = next((t for t in tenants if t['id'] != original_tenant), None)
    
    if not target_tenant:
        print("❌ Could not find a different tenant.")
        return
        
    target_tenant_id = target_tenant['id']
    print(f"   Target Tenant: {target_tenant['name']} ({target_tenant_id})")
    
    # 4. Attempt Move
    print(f"\n4. Moving Agent {agent_id} -> {target_tenant_id}...")
    
    # Hypothetical Payload - checking what the backend expects
    move_payload = {
        "targetTenantId": target_tenant_id
    }
    
    # Try the most likely endpoint structure
    move_url = f"{BASE_URL}/agents/{agent_id}/move" 
    
    print(f"   PUT {move_url}")
    resp = requests.put(move_url, json=move_payload, headers=headers)
    
    print(f"   Status Code: {resp.status_code}")
    print(f"   Response: {resp.text}")
    
    if resp.status_code == 200:
        print("✅ Move successful (supposedly). Verifying...")
        # Verify
        resp = requests.get(f"{BASE_URL}/agents/{agent_id}", headers=headers)
        updated_agent = resp.json()
        if updated_agent.get("tenant_id") == target_tenant_id:
             print("✅ Verification CONFIRMED: Tenant ID updated.")
        else:
             print(f"❌ Verification FAILED: Tenant ID is still {updated_agent.get('tenant_id')}")

if __name__ == "__main__":
    run_verification()
