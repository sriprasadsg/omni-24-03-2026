import requests
import json
import datetime

# Configuration
API_BASE = "http://localhost:5000"
AGENT_ID = "EILT0197" # Using the ID seen in logs
TENANT_ID = "exafluence" # Assuming default tenant

def force_sync():
    print(f"Sending heartbeat for {AGENT_ID}...")
    
    url = f"{API_BASE}/api/agents/{AGENT_ID}/heartbeat"
    
    payload = {
        "version": "2.0.0",
        "hostname": "DESKTOP-TEST",
        "tenantId": TENANT_ID,
        "platform": "Windows",
        "ipAddress": "192.168.1.100",
        "tamper_checks_passed": True,
        "checksum": "manual_override"
    }
    
    try:
        resp = requests.post(url, json=payload)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    force_sync()
