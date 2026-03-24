import sys
import os
import time
import requests

sys.path.append(os.path.join(os.getcwd(), 'agent'))
from capabilities.compliance import ComplianceEnforcementCapability

def force_compliance_push():
    print("Initialize Compliance Capability...")
    cap = ComplianceEnforcementCapability({})
    
    print("Collecting data...")
    result = cap.collect()
    
    hostname = "srihari-laptop"
    agent_id = f"agent-{hostname}"
    
    payload = {
        "compliance_checks": result.get("compliance_checks", []),
        "total_checks":      result.get("total_checks", 0),
        "passed":            result.get("passed", 0),
        "failed":            result.get("failed", 0),
        "compliance_score":  result.get("compliance_score", 0),
        "timestamp":         time.strftime('%Y-%m-%dT%H:%M:%S%z')
    }
    
    print(f"Collected {payload['total_checks']} checks. Sending to backend...")
    
    url = f"http://127.0.0.1:5000/api/agents/{agent_id}/instructions/result"
    headers = {"Authorization": f"Bearer temp_token"}
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        print(f"Response: {response.status_code}")
        print(response.text)
    except Exception as e:
        print(f"Error sending: {e}")

if __name__ == "__main__":
    force_compliance_push()
