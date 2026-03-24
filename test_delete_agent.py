import requests
import json

BASE_URL = "http://localhost:5000"
EMAIL = "super@omni.ai"
PASSWORD = "password123"
AGENT_ID = "agent-EILT0197"

def test_delete():
    # 1. Login
    print(f"Logging in as {EMAIL}...")
    auth_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": EMAIL,
        "password": PASSWORD
    })
    
    if auth_resp.status_code != 200:
        print(f"Login failed: {auth_resp.text}")
        return
        
    token = auth_resp.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}
    print("Login success.")
    
    # 2. Check if agent exists
    print(f"Checking existence of {AGENT_ID}...")
    get_resp = requests.get(f"{BASE_URL}/api/agents", headers=headers)
    agents = get_resp.json()
    items = agents.get("items", []) if isinstance(agents, dict) else agents
    
    found = any(a.get("id") == AGENT_ID for a in items)
    if not found:
        print(f"Agent {AGENT_ID} not found in list. Cannot delete.")
        # Create dummy if needed?
        return

    print(f"Agent found. Attempting DELETE...")
    
    # 3. Delete Agent
    del_resp = requests.delete(f"{BASE_URL}/api/agents/{AGENT_ID}", headers=headers)
    
    print(f"DELETE Response Code: {del_resp.status_code}")
    print(f"DELETE Response Body: {del_resp.text}")

if __name__ == "__main__":
    test_delete()
