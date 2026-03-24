
import requests
import json
import time

BASE_URL = "http://localhost:5000"
TOKEN_FILE = "token.txt"

ALL_FEATURES = [
    "metrics_collection", "log_collection", "fim", "vulnerability_scanning",
    "compliance_enforcement", "runtime_security", "predictive_health", "ueba",
    "sbom_analysis", "system_patching", "software_management", "network_discovery",
    "persistence_detection", "process_injection_simulation"
]

def get_token():
    with open(TOKEN_FILE, "r") as f:
        return f.read().strip()

def test_admin_control():
    print("="*50)
    print("TESTING ADMIN CAPABILITY CONTROL")
    print("="*50)

    token = get_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    # 1. Get Agent
    print("\n1. Finding Agent...")
    resp = requests.get(f"{BASE_URL}/api/agents", headers=headers)
    if resp.status_code != 200:
        print(f"FAILED to list agents: {resp.text}")
        return
    
    agents = resp.json()
    items = agents.get("items", agents) if isinstance(agents, dict) else agents
    
    if not items:
        print("No agents found.")
        return
        
    agent = items[0]
    agent_id = agent["id"]
    print(f"Target Agent: {agent['hostname']} ({agent_id})")
    
    # 2. Disable All Features (Enable only 'metrics_collection')
    print("\n2. Disabling Capabilities (Setting only 'metrics_collection')...")
    payload = {"capabilities": ["metrics_collection"]}
    resp = requests.put(f"{BASE_URL}/api/agents/{agent_id}", headers=headers, json=payload)
    
    if resp.status_code == 200:
        print("UPDATE SUCCESS")
    else:
        print(f"UPDATE FAILED: {resp.status_code} - {resp.text}")
        return

    # 3. Verify Config Endpoint (What the agent sees)
    print("\n3. Verifying Agent Config Endpoint...")
    resp = requests.get(f"{BASE_URL}/api/agents/{agent_id}/capabilities/configuration", headers=headers)
    if resp.status_code == 200:
        config = resp.json()
        caps = config.get("enabledCapabilities", [])
        print(f"Agent sees: {caps}")
        if len(caps) == 1 and "metrics_collection" in caps:
            print("VERIFIED: Agent config reflects changes.")
        else:
            print("FAILED: Config mismatch.")
    else:
        print(f"FAILED to fetch config: {resp.status_code}")

    # 4. Restore All Features
    print("\n4. Restoring All 14+ Features...")
    payload = {"capabilities": ALL_FEATURES}
    resp = requests.put(f"{BASE_URL}/api/agents/{agent_id}", headers=headers, json=payload)
    
    if resp.status_code == 200:
        print("RESTORE SUCCESS")
        
        # Verify again
        resp = requests.get(f"{BASE_URL}/api/agents/{agent_id}/capabilities/configuration")
        config = resp.json()
        caps = config.get("enabledCapabilities", [])
        print(f"Agent sees: {len(caps)} capabilities")
        if len(caps) >= 14:
            print("SUCCESS: All features enabled.")
    else:
        print(f"RESTORE FAILED: {resp.text}")

if __name__ == "__main__":
    try:
        test_admin_control()
    except Exception as e:
        print(f"Test Exception: {e}")
