import requests

def test_ransomware_rollback():
    print("Logging in to platform...")
    # Login as admin@sriprasad.com
    res = requests.post("http://localhost:5000/api/auth/token", data={
        "username": "admin@sriprasad.com",
        "password": "Admin123!"
    })
    
    if res.status_code != 200:
        print(f"Login failed: {res.text}")
        return
        
    token = res.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    print("Login successful. Checking agents...")
    
    # Get an agent ID
    res = requests.get("http://localhost:5000/api/agents", headers=headers)
    agents = res.json()
    if not agents:
        print("No agents currently registered to test against.")
        # But we will still try to hit the endpoint to verify it accepts the structure
        agent_id = "test-agent-id"
    else:
        agent_id = agents[0]["id"]
        print(f"Found agent {agent_id}. Dispatching Rollback...")
        
    # Dispatch rollback action
    payload = {
        "agent_id": agent_id,
        "action": "rollback_ransomware",
        "params": {},
        "reason": "API Verification Test"
    }
    
    res = requests.post("http://localhost:5000/api/response/execute", json=payload, headers=headers)
    print(f"Rollback dispatch returned {res.status_code}: {res.text}")
    
    if res.status_code == 200:
        print("✅ Backend successfully queued the Ransomware Rollback task!")
    else:
        print("❌ Rollback task failed.")

if __name__ == "__main__":
    test_ransomware_rollback()
