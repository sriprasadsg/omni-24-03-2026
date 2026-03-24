import requests
import json

BASE_URL = "http://localhost:5000"

def login():
    try:
        # Try Super Admin
        print("Attempting Super Admin Login...")
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "super@omni.ai",
            "password": "password123"
        })
        if resp.status_code == 200:
            return resp.json().get("access_token")
        else:
            print(f"Super Admin Login failed: {resp.status_code} - {resp.text}")

        # Try admin
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@example.com",
            "password": "admin"
        })
        if resp.status_code == 200:
            return resp.json().get("access_token")
            
        print(f"Login failed: {resp.status_code} - {resp.text}")
        return None
    except Exception as e:
        print(f"Connection error: {e}")
        return None

def test_compliance(token, asset_id):
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{BASE_URL}/api/assets/{asset_id}/compliance"
    print(f"\nTesting {url}...")
    try:
        resp = requests.get(url, headers=headers)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"Records found: {len(data)}")
            if len(data) > 0:
                print("First record sample:", json.dumps(data[0], indent=2))
        else:
            print("Error:", resp.text)
    except Exception as e:
        print(f"Request failed: {e}")

def check_agent_status(token, hostname):
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{BASE_URL}/api/agents?page_size=100"
    print(f"\nChecking Agent Status for {hostname}...")
    try:
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            agents = data.get("items", []) # paginated
            found = False
            for agent in agents:
                if agent.get("hostname") == hostname:
                    print(f"FOUND AGENT: {agent.get('hostname')}")
                    print(f"  ID: {agent.get('id')}")
                    print(f"  Status: {agent.get('status')}")
                    print(f"  Last Seen: {agent.get('lastSeen')}")
                    print(f"  Version: {agent.get('version')}")
                    print(f"  Capabilities: {len(agent.get('capabilities', []))}")
                    found = True
                    break
            if not found:
                print(f"Agent {hostname} not found in first 100 agents.")
        else:
            print(f"Error fetching agents: {resp.status_code}")
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    token = login()
    if token:
        print("Logged in successfully.")
        # Test with and without prefix
        test_compliance(token, "EILT0197")
        # test_compliance(token, "asset-EILT0197")
        check_agent_status(token, "EILT0197")
    else:
        print("Could not log in.")
