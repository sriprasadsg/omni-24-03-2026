import requests
import datetime
import time

BASE_URL = "http://localhost:5000"

def verify_ueba_shadow():
    print("--- Verifying UEBA & Shadow AI ---")
    
    # 1. Login (Super Admin)
    # Note: UEBA endpoints might not require auth in this quick dev version, 
    # but let's assume valid agent or admin flow.
    # Looking at ueba_service.py, it doesn't use dependencies in the router definition,
    # but app.py might enforce it globally or not. Let's try without token first for agent simulation.
    
    # --- Test 1: Shadow AI Detection ---
    print("\n[1] Simulating Shadow AI Event...")
    shadow_payload = {
        "agent_id": "agent-test-01",
        "process": "curl.exe",
        "remote_ip": "104.18.2.161",
        "remote_host": "api.openai.com",
        "timestamp": datetime.datetime.utcnow().isoformat()
    }
    
    try:
        resp = requests.post(f"{BASE_URL}/api/ueba/shadow-ai", json=shadow_payload)
        if resp.status_code == 200:
            print("Shadow AI Event Reported: OK")
        else:
            print(f"Shadow AI Report Failed: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"Connection Error: {e}")
        return

    # --- Test 2: Anomalous Login (UEBA) ---
    print("\n[2] Simulating Anomalous Login (3 AM)...")
    # Force 3 AM timestamp
    anomaly_time = datetime.datetime.utcnow().replace(hour=3, minute=15).isoformat()
    
    login_payload = {
        "user_id": "bob@acme.com",
        "ip_address": "45.33.22.11", # Random external IP
        "user_agent": "Mozilla/5.0 (Unknown OS) Bot/1.0",
        "timestamp": anomaly_time
    }
    
    try:
        resp = requests.post(f"{BASE_URL}/api/ueba/analyze-login", json=login_payload)
        data = resp.json()
        print(f"Analysis Result: score={data.get('risk_score')}, anomalous={data.get('is_anomalous')}")
        
        if data.get("is_anomalous") and "Off-hours login" in str(data.get("reasons")):
            print("UEBA Logic Verification: PASSED")
        else:
            print(f"UEBA Logic Verification: FAILED - {data}")
            
    except Exception as e:
        print(f"UEBA connection error: {e}")

    # --- Test 3: Verify Stats ---
    print("\n[3] Verifying Dashboard Stats...")
    try:
        resp = requests.get(f"{BASE_URL}/api/ueba/stats")
        if resp.status_code == 200:
            stats = resp.json()
            print(f"Stats: {stats}")
            if stats["shadow_ai_detections"] > 0:
                print("Shadow AI Stats Verification: PASSED")
        else:
            print(f"Stats Failed: {resp.status_code}")
    except Exception as e:
         print(f"Stats connection error: {e}")

if __name__ == "__main__":
    verify_ueba_shadow()
