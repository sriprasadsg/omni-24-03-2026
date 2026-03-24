import requests
import json

BASE_URL = "http://localhost:5000"

def get_token():
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "super@omni.ai",
        "password": "password123"
    })
    return resp.json()["access_token"]

def verify_dynamic_goals():
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    print("[1] Fetching Agents...")
    resp = requests.get(f"{BASE_URL}/api/agents", headers=headers)
    agents = resp.json()
    
    if not agents or len(agents) == 0:
        print("No agents found. Using fallback check.")
        agent_id = "test-agent-persistence"
    else:
        # Use a real agent if available
        # The paginated response might have 'items'
        items = agents.get('items', agents)
        agent_id = items[0]['id'] if items else "test-agent-persistence"

    print(f"[2] Fetching dynamic goals for agent: {agent_id}...")
    resp = requests.get(f"{BASE_URL}/api/agents/{agent_id}/goals", headers=headers)
    
    if resp.status_code == 200:
        goals = resp.json()
        print(f"PASS: Received {len(goals)} goals from AI.")
        print(json.dumps(goals, indent=2))
    else:
        print(f"FAIL: Status {resp.status_code} - {resp.text}")

if __name__ == "__main__":
    verify_dynamic_goals()
