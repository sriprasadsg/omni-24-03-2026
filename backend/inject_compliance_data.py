
import requests
import json
import hashlib
import time

AGENT_ID = "agent-EILT0197"
API_URL = "http://localhost:5000/api/agents"

def inject_data():
    print(f"Injecting compliance data for {AGENT_ID}...")
    
    # Create sample evidence content
    raw_content = "Windows Firewall is ENABLED on all profiles."
    content_hash = hashlib.sha256(raw_content.encode('utf-8')).hexdigest()
    
    payload = {
        "id": AGENT_ID,
        "hostname": "EILT0197",
        "ipAddress": "192.168.0.102",  # From screenshot
        "status": "Online",
        "version": "1.0.0",
        "platform": "Windows",
        "meta": {
            "compliance_enforcement": [
                {
                    "check": "Windows Firewall",
                    "status": "Pass",
                    "details": "Firewall active on Domain, Private, Public.",
                    "evidence_content": raw_content,
                    "content_hash": content_hash,
                    "timestamp": time.time()
                },
                {
                    "check": "Audit Policy",
                    "status": "Fail",
                    "details": "Audit Object Access is NOT configured.",
                    "evidence_content": "Audit Object Access: No Auditing",
                    "content_hash": hashlib.sha256(b"Audit Object Access: No Auditing").hexdigest(),
                    "timestamp": time.time()
                }
            ],
            # Add some other meta to populate Overview
            "os_version": "Windows 11 Pro 23H2",
            "installed_software": [
                {"name": "Google Chrome", "version": "120.0.6099.130", "installDate": "2024-01-15", "updateAvailable": True, "latestVersion": "121.0.0.0"},
                {"name": "Visual Studio Code", "version": "1.85.1", "installDate": "2023-12-20"}
            ]
        }
    }
    
    try:
        resp = requests.post(f"{API_URL}/{AGENT_ID}/heartbeat", json=payload)
        if resp.status_code == 200:
            print("✅ Data Injected Successfully!")
        else:
            print(f"❌ Failed: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    inject_data()
