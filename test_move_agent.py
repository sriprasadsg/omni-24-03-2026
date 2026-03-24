
import requests
import jwt
import datetime
import sys

# Configuration
API_BASE = "http://localhost:5000/api"
SECRET_KEY = "enterprise-omni-agent-secret-key-change-me"  # From authentication_service.py

def create_token(role="super_admin", tenant_id="platform-admin"):
    payload = {
        "sub": "admin",
        "role": role,
        "tenant_id": tenant_id,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def test_move_agent():
    print("--- Testing Move Agent Endpoint ---")
    
    # 1. Setup Auth
    token = create_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    # 2. Get available tenants
    print("\nFetching tenants...")
    res = requests.get(f"{API_BASE}/tenants", headers=headers)
    if res.status_code != 200:
        print(f"Failed to fetch tenants: {res.text}")
        return
        
    tenants = res.json()
    print(f"DEBUG: Tenants found: {len(tenants)}")
    for i, t in enumerate(tenants):
        print(f" - [{i}] {t}")

    if len(tenants) < 2:
        print("Need at least 2 tenants to test move.")
        # Create a temp tenant
        print("Creating temp tenant...")
        try:
            res = requests.post(f"{API_BASE}/tenants", json={
                "name": "Temp Target Tenant", 
                "subscriptionTier": "Pro"
            }, headers=headers)
            target_tenant = res.json()
            # Append to local list for later logic if needed or just use it
        except Exception as e:
             print(f"Failed to create tenant: {e}")
             return
    else:
        target_tenant = tenants[1] # Pick the second one
        
    source_tenant = tenants[0]
    print(f"Source: {source_tenant.get('id')}")
    print(f"Target: {target_tenant.get('id')}")
    
    if not source_tenant.get('id') or not target_tenant.get('id'):
        print("CRITICAL: Missing tenant ID. Aborting.")
        return
    print(f"Source Tenant: {source_tenant['id']} ({source_tenant['name']})")
    print(f"Target Tenant: {target_tenant['id']} ({target_tenant['name']})")
    
    # 3. Get or Register an Agent
    print("\nGetting existin agents...")
    res = requests.get(f"{API_BASE}/agents", headers=headers)
    agents = res.json().get("items", [])
    
    if not agents:
        print("No agents found. Registering one...")
        # Needs registration key from source tenant
        reg_key = source_tenant["registrationKey"]
        res = requests.post(f"{API_BASE}/agents/register", json={
            "registrationKey": reg_key,
            "hostname": "test-move-agent",
            "platform": "Linux",
            "version": "1.0.0"
        })
        if res.status_code != 200:
            print(f"Failed to register agent: {res.text}")
            return
        # Fetch again to get ID
        res = requests.get(f"{API_BASE}/agents", headers=headers)
        agents = res.json().get("items", [])
        
    test_agent = agents[0]
    print(f"Test Agent: {test_agent['id']} (Current Tenant: {test_agent['tenantId']})")
    
    # Ensure it's not already in target
    if test_agent['tenantId'] == target_tenant['id']:
        print("Agent already in target. Switching target...")
        target_tenant = source_tenant # Swap
    
    print(f"Moving Agent to: {target_tenant['id']}")
    
    # 4. Perform Move
    res = requests.put(
        f"{API_BASE}/agents/{test_agent['id']}/move",
        json={"targetTenantId": target_tenant['id']},
        headers=headers
    )
    
    if res.status_code == 200:
        print("Move SUCCESS:")
        print(res.json())
    else:
        print(f"Move FAILED ({res.status_code}):")
        print(res.text)
        return

    # 5. Verify
    print("\nVerifying...")
    res = requests.get(f"{API_BASE}/agents", headers=headers)
    agents = res.json().get("items", [])
    updated_agent = next((a for a in agents if a['id'] == test_agent['id']), None)
    
    if updated_agent:
        print(f"Updated Agent Tenant: {updated_agent['tenantId']}")
        if updated_agent['tenantId'] == target_tenant['id']:
            print("VERIFICATION PASSED!")
        else:
            print("VERIFICATION FAILED: Tenant ID did not change in list.")
    else:
        print("Agent not found in list!")

    # Cleanup (Move back?)
    # Optional

if __name__ == "__main__":
    test_move_agent()
