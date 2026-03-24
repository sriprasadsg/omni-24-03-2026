
import requests
import json
import time

API_BASE = "http://localhost:5000"

def verify_refresh_scan():
    # 1. Get an agent ID (using EILT0197 as it's known)
    agent_id = "agent-EILT0197" 
    
    print(f"Testing Compliance Refresh for Agent: {agent_id}")
    
    url = f"{API_BASE}/api/agents/{agent_id}/compliance/scan"
    
    try:
        res = requests.post(url)
        print(f"POST {url} -> Status: {res.status_code}")
        
        if res.status_code == 200:
            data = res.json()
            print("Response:", json.dumps(data, indent=2))
            
            if data['success']:
                print("✅ TEST PASSED: Scan instruction sent successfully.")
            else:
                print("❌ TEST FAILED: Success flag is false.")
        else:
            print(f"❌ TEST FAILED: Backend returned {res.status_code}")
            print(res.text)
            
    except Exception as e:
        print(f"❌ TEST FAILED: Exception: {e}")

if __name__ == "__main__":
    verify_refresh_scan()
