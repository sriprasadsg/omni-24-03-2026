
import requests
import time
import json

BASE_URL = "http://localhost:5000"

def login():
    try:
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "super@omni.ai",
            "password": "password123"
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        else:
            print("Login failed")
            return None
    except Exception as e:
        print(f"Login error: {e}")
        return None

def verify_loop():
    token = login()
    if not token:
        return

    headers = {"Authorization": f"Bearer {token}"}

    # 1. Trigger Scan
    print("Triggering Compliance Scan...")
    resp = requests.post(f"{BASE_URL}/api/compliance-automation/collect-evidence", 
                         json={"framework_id": "nistcsf", "tenant_id": "default"}, 
                         headers=headers)
    print(f"Trigger Response: {resp.status_code} - {resp.text}")

    # 2. Wait for Agent to Poll and Reply
    print("Waiting for agent to process (30s)...")
    time.sleep(30)

    # 3. Check Compliance Data
    print("Checking Asset Compliance...")
    # We need an endpoint to fetch compliance data. 
    # FrameworkDetail.tsx uses assetComplianceData passed as props, usually fetched via something.
    # Let's check apiService.ts: probably fetchGlobalComplianceData or similar?
    # Or just check /api/compliance/frameworks/nistcsf/assets (hypothetically)
    
    # Actually, let's just use the `compliance_automation_api.py` endpoint if there is one, 
    # or check the database directly via a separate helper if needed.
    # But for now, let's try to fetch framework details which usually includes compliance stats.
    
    # FrameworkDetail fetches `fetchComplianceFrameworks`? No, that's high level.
    # FrameworkDetail Props: `assetComplianceData`
    # In App.tsx: `api.fetchGlobalComplianceData()`?
    
    # Let's check `api.fetchGlobalComplianceData()` implementation in apiService if possible.
    # But I can just check the new endpoint I created? No, I created `submit`.
    # Let's check `get_framework_evidence`.
    
    resp = requests.get(f"{BASE_URL}/api/compliance-automation/evidence/nistcsf?tenant_id=default", headers=headers)
    print(f"Evidence Response: {resp.status_code}")
    evidence = resp.json()
    print(f"Evidence count: {len(evidence)}")
    if len(evidence) > 0:
        print("SUCCESS: Evidence found!")
        print(evidence[0])
    else:
        print("FAILURE: No evidence found.")

if __name__ == "__main__":
    verify_loop()
