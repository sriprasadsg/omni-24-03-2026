import requests
import time
import json
import jwt

BASE_URL = "http://localhost:5000/api"

# Token from config.yaml (The new one)
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbkBleGFmbHVlbmNlLmNvbSIsInJvbGUiOiJUZW5hbnQgQWRtaW4iLCJ0ZW5hbnRfaWQiOiJ0ZW5hbnRfODJkZGEwZjMzYmM0IiwiZXhwIjoxNzY5NzY1NjYwfQ.K0iGj_U-tGk2f8QWdxapTAjduHDsD1NdjzNNI-63870"

def run_heartbeat():
    print(f"Testing Heatbeat to {BASE_URL}")
    
    # 1. Decode token to verify tenant
    try:
        payload = jwt.get_unverified_claims(TOKEN)
        print(f"Token Tenant: {payload.get('tenant_id')}")
    except Exception as e:
        print(f"Token decode error: {e}")

    # 2. Prepare Payload
    # Using hostname "EILT0197" as per previous findings
    data = {
        "hostname": "EILT0197",
        "ipAddress": "172.29.192.1",
        "platform": "Windows",
        "version": "2.0.0",
        "status": "Online",
        "meta": {
            "cpu_load": 10.5,
            "verification": "manual_script"
        }
    }
    
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }
    
    # Agent ID from DB (EILT0197 or agent-EILT0197?)
    # Based on Agent code, it might use "agent-[hostname]"
    # Based on DB check, id="agent-..." or id="EILT0197"?
    # check_agent_status_debug.py output said: Agent: EILT0197
    # Let's try BOTH IDs.
    
    agent_ids = ["EILT0197", "agent-EILT0197"]
    
    for agent_id in agent_ids:
        print(f"\n--- Sending Heartbeat for ID: {agent_id} ---")
        url = f"{BASE_URL}/agents/{agent_id}/heartbeat"
        try:
            res = requests.post(url, json=data, headers=headers)
            print(f"Status: {res.status_code}")
            print(f"Response: {res.text}")
        except Exception as e:
            print(f"Request Exception: {e}")

if __name__ == "__main__":
    run_heartbeat()
