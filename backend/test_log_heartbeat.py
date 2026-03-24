import requests
import json
import time
from datetime import datetime

API_BASE_URL = "http://localhost:5000"
REGISTRATION_KEY = "reg_62a4b18a91ec461b"
AGENT_ID = "test-agent-logs"

headers = {
    "X-Tenant-Key": REGISTRATION_KEY,
    "Content-Type": "application/json"
}

heartbeat_payload = {
    "hostname": "test-host",
    "tenantId": "default",
    "status": "Online",
    "platform": "Windows",
    "version": "2.0.1",
    "ipAddress": "127.0.0.1",
    "meta": {
        "log_collection": [
            {
                "service": "nginx",
                "level": "INFO",
                "message": f"GET /api/v1/resource HTTP/1.1 200 - Test Log {int(time.time())}",
                "timestamp": datetime.now().isoformat()
            }
        ],
        "persistence_detection": {
            "findings": [
                {
                    "type": "Registry Run Key",
                    "location": "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run",
                    "name": "MaliciousTask",
                    "command": "C:\\Users\\Public\\malicious.exe",
                    "severity": "High"
                }
            ],
            "count": 1,
            "platform": "nt"
        },
        "ueba": {
            "anomalies_detected": [
                {
                    "type": "Potential Brute Force",
                    "user": "admin",
                    "failed_attempts": 10,
                    "severity": "High"
                }
            ],
            "security_events": [],
            "failed_login_attempts": 10,
            "monitored_users": 1
        },
        "shadow_ai": {
            "ai_connections": [
                {
                    "process": "python.exe",
                    "remote_ip": "104.18.23.205",
                    "remote_host": "api.openai.com",
                    "timestamp": datetime.now().isoformat()
                }
            ],
            "detected_count": 1
        }
    }
}

def test_heartbeat_logs():
    print(f"Sending heartbeat to {API_BASE_URL}/api/agents/{AGENT_ID}/heartbeat")
    response = requests.post(
        f"{API_BASE_URL}/api/agents/{AGENT_ID}/heartbeat",
        headers=headers,
        json=heartbeat_payload
    )
    
    print(f"Heartbeat response: {response.status_code}")
    print(response.text)
    
    if response.status_code == 200:
        print("Heartbeat sent successfully.")
    else:
        print("Failed to send heartbeat.")

if __name__ == "__main__":
    test_heartbeat_logs()
