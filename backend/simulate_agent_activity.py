
import requests
import json
import time
import random
import uuid
from datetime import datetime

# Configuration
API_URL = "http://localhost:5000/api"
TENANT_ID = "tenant-default" # Repalce if needed
HOSTNAME = "agent-sim-compliance-xp"

def register_agent():
    print(f"Registering agent {HOSTNAME}...")
    url = f"{API_URL}/agents/register"
    payload = {
        "registrationKey": "reg-default-key", # Assuming default
        "hostname": HOSTNAME,
        "platform": "Linux",
        "version": "2.1.0",
        "ipAddress": "10.0.0.155",
        "macAddress": "00:50:56:C0:00:08",
        "meta": {
            "os_info": {"name": "Ubuntu", "version": "22.04 LTS"}
        }
    }
    
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print(f"✅ Registered: {response.json()}")
            return response.json().get("agentId")
        else:
            print(f"❌ Registration Failed: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Connection Error: {e}")
        return None

def send_compliance_report(agent_id, tenant_key="reg-default-key"):
    print(f"Sending Expanded Compliance Report for {HOSTNAME}...")
    url = f"{API_URL}/agents/{HOSTNAME}/instructions/result"
    
    # Headers for legacy auth or new auth
    headers = {
        "X-Tenant-Key": tenant_key
    }
    
    payload = {
        "agent_id": agent_id,
        "instruction_id": "inst-sim-123",
        "status": "completed",
        "compliance_checks": [
            # 1. Cloud Metadata (FedRAMP / CSA STAR)
            {
                "check": "Cloud Instance Metadata",
                "status": "Pass",
                "details": "Instance ID: i-0abc123; Region: us-east-1; IMDSv2: Enabled",
                "evidence_content": json.dumps({"instanceId": "i-0abc123", "imageId": "ami-123", "imds": "required"}),
                "content_hash": "a1b2c3d4"
            },
            {
                "check": "Public IP Exposure",
                "status": "Pass",
                "details": "No public IPv4 assigned. VPC Interface Endpoint used.",
                "evidence_content": "interface=eth0; ipv4=10.0.0.155; public_ipv4=None",
                "content_hash": "e5f6g7h8"
            },
            
            # 2. PII Discovery (CCPA / GDPR)
            {
                "check": "PII Data Discovery",
                "status": "Warning",
                "details": "Potential credit card numbers found in /var/log/app.log",
                "evidence_content": "Match: Credit Card\nFile: /var/log/app.log\nLines: 405, 412\nSample: ****-****-****-1234",
                "content_hash": "i9j0k1l2"
            },
            {
                "check": "Unencrypted PII",
                "status": "Fail",
                "details": "/tmp/customers.csv contains cleartext PII",
                "evidence_content": "File: /tmp/customers.csv\nEncryption: None\nOwner: root:root\nPermissions: 644",
                "content_hash": "m3n4o5p6"
            },
            
            # 3. Integrity (CMMC / PCI)
            {
                "check": "File Integrity Monitoring",
                "status": "Pass",
                "details": "No unauthorized changes to /etc/* in last 24h",
                "evidence_content": "Scanned: 1450 files\nChanged: 0\nBaseline: bl-2023-10-01",
                "content_hash": "q7r8s9t0"
            },
            
            # 4. Logging (DORA)
            {
                "check": "Log Shipping Status",
                "status": "Pass",
                "details": "Fluent Bit service running and connected to Splunk",
                "evidence_content": "Service: fluent-bit\nStatus: Active (Running)\nOutput: splunk.internal:8088",
                "content_hash": "u1v2w3x4"
            },
            
            # 5. Configuration (COBIT)
            {
                "check": "Configuration Audit",
                "status": "Pass",
                "details": "Matches Gold Image v3.2",
                "evidence_content": "Drift: 0%\nImageID: gold-linux-3.2\nLastSync: 2023-11-15T10:00:00Z",
                "content_hash": "y5z6a7b8"
            }
        ]
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            print(f"✅ Report Sent: {response.json()}")
        else:
            print(f"❌ Report Failed: {response.text}")
    except Exception as e:
        print(f"❌ Connection Error: {e}")

if __name__ == "__main__":
    agent_id = register_agent()
    if agent_id:
        time.sleep(1)
        send_compliance_report(agent_id)
