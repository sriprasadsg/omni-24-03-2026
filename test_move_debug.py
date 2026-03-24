
import requests
import jwt
import datetime
import json
import sys

API_BASE = "http://localhost:5000/api"
SECRET_KEY = "enterprise-omni-agent-secret-key-change-me"

def create_token(role="super_admin", tenant_id="tenant_default"):
    payload = {
        "sub": "admin",
        "role": role,
        "tenant_id": tenant_id,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def log(msg):
    with open("test_output.txt", "a") as f:
        f.write(msg + "\n")
    print(msg)

def test():
    open("test_output.txt", "w").close() # Clear
    log("--- START DEBUG ---")
    
    token = create_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    # List Tenants
    log("GET /tenants")
    try:
        res = requests.get(f"{API_BASE}/tenants", headers=headers)
        log(f"Status: {res.status_code}")
        log(f"Response: {res.text}")
        tenants = res.json()
    except Exception as e:
        log(f"Exception: {e}")
        return

    if not isinstance(tenants, list):
        log("Tenants is not a list. Auth failed?")
        return

    target_tenant = None
    if len(tenants) < 2:
        log("Creating tenant...")
        try:
            res = requests.post(f"{API_BASE}/tenants", json={
                "name": "Temp Target Debug", 
                "subscriptionTier": "Pro"
            }, headers=headers)
            log(f"Create Status: {res.status_code}")
            log(f"Create Response: {res.text}")
            target_tenant = res.json()
        except Exception as e:
            log(f"Create Exception: {e}")
            return
    else:
        log("Using existing 2nd tenant")
        target_tenant = tenants[1]

    source_tenant = tenants[0]
    
    agent_id = None
    # Get Agent
    res = requests.get(f"{API_BASE}/agents", headers=headers)
    agents = res.json().get("items", [])
    if agents:
        agent_id = agents[0]['id']
        log(f"Using Agent: {agent_id} (Tenant: {agents[0]['tenantId']})")
    else:
        log("No agents found. Skipping Move.")
        return

    tid = target_tenant.get('id')
    if not tid:
        log(f"Target tenant has no ID. Object: {target_tenant}")
        return

    log(f"Moving to: {tid}")
    res = requests.put(
        f"{API_BASE}/agents/{agent_id}/move",
        json={"targetTenantId": tid},
        headers=headers
    )
    log(f"Move Status: {res.status_code}")
    log(f"Move Response: {res.text}")

if __name__ == "__main__":
    test()
