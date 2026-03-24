import requests
import json
import uuid
from datetime import datetime

BASE_URL = "http://localhost:5000"
AGENT_HOSTNAME = "simulation-agent-01"

def login():
    """Login and return headers with token"""
    print(f"Logging in to {BASE_URL}...")
    try:
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "super@omni.ai",
            "password": "password123"
        })
        if response.status_code == 200:
            token = response.json().get("access_token")
            print("Login successful.")
            return {"Authorization": f"Bearer {token}"}
        else:
            print(f"Login failed: {response.text}")
            return None
    except Exception as e:
        print(f"Login exception: {e}")
        return None

def verify_logs():
    headers = login()
    if not headers:
        return

    # 1. Test Ingestion (POST)
    print(f"\nTesting POST {BASE_URL}/api/logs...")
    test_id = f"test-log-{uuid.uuid4().hex[:8]}"
    payload = {
        "severity": "INFO",
        "service": "verify_script",
        "hostname": "verification-host",
        "message": f"Verification log entry {test_id}",
        "metadata": {"source": "script"}
    }
    
    try:
        response = requests.post(f"{BASE_URL}/api/logs", json=payload, headers=headers)
        if response.status_code == 200:
            print("PASSED: Log ingestion successful.")
            print(response.json())
        else:
            print(f"FAILED: Log ingestion failed code {response.status_code}")
            print(response.text)
            return
    except Exception as e:
        print(f"FAILED: POST Exception: {e}")
        return

    # 2. Test Retrieval (GET)
    print(f"\nTesting GET {BASE_URL}/api/logs...")
    try:
        response = requests.get(f"{BASE_URL}/api/logs", headers=headers)
        if response.status_code != 200:
            print(f"FAILED: Status code {response.status_code}")
            print(response.text)
            return

        logs = response.json()
        print(f"Success: Retrieved {len(logs)} logs.")
        
        # Verify our log is there
        found = False
        print(f"Searching for logs from {AGENT_HOSTNAME}...")
        for log in logs:
            # Check for logs from our simulation script
            if log.get("hostname") == "simulation-agent-01":
                found = True
                print(f"PASSED: Found a log entry from {log.get('hostname')}: {log.get('message')}")
                if log.get("agentId"):
                    print(f"PASSED: Log has agentId: {log.get('agentId')}")
                else:
                    print("WARNING: Log matches hostname but missing agentId (Legacy?)")
                break
        
        if not found:
            print("FAILED: Did not find any log entry from simulation-agent-01.")

        if logs:
            print("\nSample Log Entry:")
            print(json.dumps(logs[0], indent=2))

    except Exception as e:
        print(f"FAILED: GET Exception occurred: {e}")

if __name__ == "__main__":
    verify_logs()
