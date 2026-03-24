import requests
import json
import os

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:5000")
AGENT_ID = "test-agent-logs"

def login():
    credentials = {"email": "super@omni.ai", "password": "password123"}
    try:
        response = requests.post(f"{API_BASE_URL}/api/auth/login", json=credentials)
        if response.status_code == 200:
            return response.json().get("access_token")
        print(f"Login failed: {response.text}")
        return None
    except Exception as e:
        print(f"Error logging in: {e}")
        return None

def verify_persistence(token):
    print("\n--- Verifying Persistence Findings ---")
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{API_BASE_URL}/api/persistence/results/{AGENT_ID}", headers=headers)
    if response.status_code == 200:
        data = response.json()
        print(f"Persistence Count: {data.get('count')}")
        findings = data.get("findings", [])
        print(f"Findings: {len(findings)}")
        for f in findings:
            print(f"  - [{f.get('severity')}] {f.get('type')}: {f.get('name')} at {f.get('location')}")
        if len(findings) > 0:
            print("✅ Persistence telemetry bridged correctly!")
        else:
            print("❌ No persistence findings found.")
    else:
        print(f"Failed to fetch persistence: {response.status_code} - {response.text}")

def verify_shadow_ai(token):
    print("\n--- Verifying Shadow AI Events ---")
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{API_BASE_URL}/api/ueba/shadow-ai/events", headers=headers)
    if response.status_code == 200:
        data = response.json()
        print(f"Shadow AI Event Count: {len(data)}")
        found = False
        for e in data:
            if e.get("agent_id") == AGENT_ID:
                found = True
                print(f"  - [{e.get('timestamp')}] {e.get('process')} connected to {e.get('remote_host')}")
        if found:
            print("✅ Shadow AI telemetry bridged correctly!")
        else:
            print("❌ No Shadow AI events found for test agent.")
    else:
        print(f"Failed to fetch Shadow AI events: {response.status_code} - {response.text}")

def verify_ueba_stats(token):
    print("\n--- Verifying UEBA Stats (Anomalies) ---")
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{API_BASE_URL}/api/ueba/stats", headers=headers)
    if response.status_code == 200:
        data = response.json()
        print(f"UEBA Stats: {json.dumps(data, indent=2)}")
        if data.get("login_anomalies", 0) > 0 or data.get("shadow_ai_detections", 0) > 0:
             print("✅ UEBA stats reflect bridged data!")
        else:
            print("❌ UEBA stats may not reflect the bridged anomalies yet.")
    else:
        print(f"Failed to fetch UEBA stats: {response.status_code} - {response.text}")

def run_verification():
    token = login()
    if not token:
        print("Cannot proceed without authentication.")
        return
    
    verify_persistence(token)
    verify_shadow_ai(token)
    verify_ueba_stats(token)

if __name__ == "__main__":
    run_verification()
