import requests
import time
import json
import sys

BASE_URL = "http://localhost:5000/api"
TOKEN = None

def login():
    global TOKEN
    try:
        # Login as Super Admin to get access to tenants
        res = requests.post(f"{BASE_URL}/auth/login", json={"email": "testadmin@example.com", "password": "password123"})
        if res.status_code == 200:
            TOKEN = res.json().get("access_token")
            print("[Init] Login successful.")
            return True
        else:
            print(f"[Error] Login failed: {res.text}")
            return False
    except Exception as e:
        print(f"[Error] Login exception: {e}")
        return False

def get_tenant_key(tenant_id):
    """Fetch the registration key for the target tenant (requires Admin)"""
    if not TOKEN: return None
    
    headers = {"Authorization": f"Bearer {TOKEN}"}
    try:
        # Fetch all tenants (Super Admin privilege)
        res = requests.get(f"{BASE_URL}/tenants", headers=headers)
        if res.status_code == 200:
            tenants = res.json()
            # Handle list or dict return? usually list
            if isinstance(tenants, list):
                for t in tenants:
                    if t.get("id") == tenant_id:
                        return t.get("registrationKey")
            print(f"[Warn] Tenant {tenant_id} not found in tenant list.")
        else:
            print(f"[Error] Failed to fetch tenants: {res.status_code}")
    except Exception as e:
        print(f"[Error] Get Tenant Key exception: {e}")
    return None

def get_agents():
    if not TOKEN: return []
    headers = {"Authorization": f"Bearer {TOKEN}"}
    try:
        res = requests.get(f"{BASE_URL}/agents", headers=headers)
        if res.status_code == 200:
            return res.json().get("items", [])
        print(f"[Error] Failed to fetch agents: {res.text}")
    except Exception as e:
        print(f"[Error] Get Agents exception: {e}")
    return []

def run_heartbeat():
    if not login():
        return

    agents = get_agents()
    if not agents:
        print("No agents found to simulate.")
        return

    target_agent = agents[0]
    agent_id = target_agent.get("id")
    hostname = target_agent.get("hostname", "Unknown")
    tenant_id = target_agent.get("tenantId")
    
    # Fetch key
    print(f"Fetching key for tenant: {tenant_id}...")
    tenant_key = get_tenant_key(tenant_id)
    
    if not tenant_key:
        print("[Critical] Could not retrieve Tenant Key. Heartbeat will likely fail.")
        # We continue to demonstrate the failure if key is missing (or maybe we should stop?)
        # Let's try to send invalid key if missing to show 403? 
        # But for 'Proceed with plan', we want it to WORK.
    else:
        print(f"[Success] Retrieved Tenant Key: {tenant_key[:5]}...")
    
    print(f"Starting heartbeat simulation for Agent: {hostname} ({agent_id})")
    
    while True:
        try:
            payload = {
                "ipAddress": "192.168.1.105",
                "platform": "Linux",
                "version": "1.5.0",
                "hostname": hostname,
                "meta": {
                    "cpu_load": 42.5,
                    "memory_usage": 60.1
                }
            }
            
            headers = {"X-Tenant-Key": tenant_key} if tenant_key else {}
            
            res = requests.post(f"{BASE_URL}/agents/{agent_id}/heartbeat", json=payload, headers=headers)
            
            if res.status_code == 200:
                print(f"[{time.strftime('%H:%M:%S')}] Heartbeat sent successfully.")
            elif res.status_code == 403:
                print(f"[{time.strftime('%H:%M:%S')}] Auth Failed (403): Invalid/Missing Key")
            else:
                print(f"[{time.strftime('%H:%M:%S')}] Heartbeat failed: {res.status_code} - {res.text}")
                
        except Exception as e:
             print(f"[{time.strftime('%H:%M:%S')}] Connection error: {e}")
        
        time.sleep(10)

if __name__ == "__main__":
    run_heartbeat()
