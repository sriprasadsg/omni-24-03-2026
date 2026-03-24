import requests
import json
import socket
import time

API_URL = "http://127.0.0.1:5000/api"

def run_verification():
    # 1. Login to get token
    print("1. Logging in...")
    try:
        r = requests.post(f"{API_URL}/auth/login", json={"email": "super@omni.ai", "password": "password123"})
        if r.status_code != 200:
            print(f"Login failed: {r.text}")
            return
        token = r.json().get("access_token")
        print("Login success. Token acquired.")
    except Exception as e:
        print(f"Login error: {e}")
        return

    # 2. Seed Agent
    print("\n2. Seeding Agent...")
    agent_id = f"test-agent-{int(time.time())}"
    payload = {
        "hostname": "TEST-WIN-EVIDENCE",
        "tenantId": "platform-admin",
        "status": "Online",
        "platform": "Windows",
        "version": "2.0.0",
        "ipAddress": "127.0.0.1",
        "meta": {
            "os": "Windows 10 Pro",
            "compliance_enforcement": {
                "compliance_checks": [
                    {
                        "check": "Windows Firewall Profiles",
                        "status": "Pass",
                        "details": "Firewall enabled on 3 profiles",
                        "evidence_content": "Domain: Enabled\\nPrivate: Enabled\\nPublic: Enabled\\n"
                    },
                    {
                        "check": "BitLocker Encryption",
                        "status": "Fail",
                        "details": "Protection Status: Off",
                        "evidence_content": "BitLocker Protection Status: Off"
                    }
                ],
                "compliance_score": 50.0
            }
        }
    }
    
    try:
        # Heartbeat uses tenant token logic, but here we simulate agent heartbeat. 
        # Agents usually have an agent_token. But legacy heartbeat might be open or token optional?
        # Let's check agent.py... it uses headers["Authorization"] = f"Bearer {token}".
        # But wait, initially agent sends heartbeat without token? 
        # In this environment, let's try assuming open or we use the user token just to get past the gate if it's the wrong endpoint?
        # Actually /api/agents/{id}/heartbeat might be open if configured that way, or requires agent token.
        # Let's try sending it.
        r = requests.post(f"{API_URL}/agents/{agent_id}/heartbeat", json=payload)
        print(f"Heartbeat Status: {r.status_code}")
    except Exception as e:
        print(f"Heartbeat error: {e}")

    # 3. Fetch Evidence (Authenticated)
    print("\n3. Fetching Evidence (Authenticated)...")
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{API_URL}/agents", headers=headers)
    
    if r.status_code == 200:
        agents = r.json()
        target = next((a for a in agents if a['id'] == agent_id), None)
        if target:
            print("\n=== EVIDENCE VERIFIED ===")
            print(json.dumps(target.get('meta', {}).get('compliance_enforcement', {}), indent=2))
        else:
            print("Agent not found in list.")
    else:
        print(f"Fetch failed: {r.status_code} {r.text}")

if __name__ == "__main__":
    run_verification()
