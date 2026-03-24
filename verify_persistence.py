import requests
import time
import sys

BASE_URL = "http://localhost:5000"
AGENT_ID = "test-agent-persistence"

def verify_persistence():
    print("[1] Creating Approval Request...")
    payload = {
        "agent_id": AGENT_ID,
        "action_type": "persistence_test",
        "description": "Testing MongoDB Persistence",
        "risk_score": 5.0,
        "reasoning": "Self-check",
        "details": {"test": "true"}
    }
    
    try:
        resp = requests.post(f"{BASE_URL}/api/agents/{AGENT_ID}/approval-request", json=payload)
        resp.raise_for_status()
        data = resp.json()
        req_id = data['request_id']
        print(f"Success. Request ID: {req_id}")
        
        print("[2] verifying it appears in Pending list...")
        resp = requests.get(f"{BASE_URL}/api/agents/approvals/pending")
        resp.raise_for_status()
        pending = resp.json()
        
        found = any(p['id'] == req_id for p in pending)
        if found:
            print("PASS: Request found in pending list (MongoDB).")
        else:
            print("FAIL: Request NOT found in pending list.")
            sys.exit(1)
            
    except Exception as e:
        print(f"FAIL: API Error - {e}")
        sys.exit(1)

if __name__ == "__main__":
    verify_persistence()
