import socket
import platform
import requests
import json
import uuid
import time
import random
from datetime import datetime

BASE_URL = "http://localhost:5000"
# Get actual system hostname
try:
    AGENT_HOSTNAME = socket.gethostname()
except:
    AGENT_HOSTNAME = "unknown-host"

# Get actual IP address
try:
    AGENT_IP = socket.gethostbyname(socket.gethostname())
except:
    AGENT_IP = "127.0.0.1"
print(f"Running simulation on: {AGENT_HOSTNAME} ({AGENT_IP})")

def login():
    """Login and return headers with token"""
    print(f"Logging in to {BASE_URL}...")
    try:
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@exafluence.com",
            "password": "password123"
        })
        if response.status_code == 200:
            token = response.json().get("access_token")
            print("Login successful.")
            return {"Authorization": f"Bearer {token}"}
        else:
            print(f"Login failed: {response.json()}")
            return None
    except Exception as e:
        print(f"Login exception: {e}")
        return None

def register_agent(headers):
    """Register or update the agent to ensure it exists in the fleet"""
    print(f"Registering agent {AGENT_HOSTNAME}...")
    payload = {
        "hostname": AGENT_HOSTNAME,
        "platform": "Linux",
        "version": "1.5.0",
        "ipAddress": AGENT_IP,
        "status": "Online",
        "registrationKey": "default-tenant-key", # Assuming this key exists or we need to find one. 
        # Wait, the endpoint checks for registrationKey in body if not agent flow?
        # secure_agent_endpoints.py uses Token. registration endpoint uses registrationKey.
        # Let's check if we have a key. d:\Downloads\enterprise-omni-agent-ai-platform\backend\database.py might seed it.
        # Or we can just use the token? No, register_agent endpoint requires registrationKey.
    }
    
    # We need a registration key.
    # Let's try to fetch tenant info first to get a key?
    # Admin can see tenants.
    try:
        tenants_resp = requests.get(f"{BASE_URL}/api/tenants", headers=headers)
        if tenants_resp.status_code == 200:
            tenants = tenants_resp.json()
            exa_tenant = next((t for t in tenants if t.get("name") == "Exafluence"), None)
            if exa_tenant:
                key = exa_tenant.get("registrationKey")
                payload["registrationKey"] = key
                print(f"Using registration key: {key}")
            elif tenants:
                key = tenants[0].get("registrationKey")
                print("No tenants found! Cannot register.")
                return None
        else:
             print(f"Failed to fetch tenants: {tenants_resp.status_code}")
             # valid key might be hardcoded in seed?
             payload["registrationKey"] = "default-key"
    except:
        payload["registrationKey"] = "default-key"

    try:
        resp = requests.post(f"{BASE_URL}/api/agents/register", json=payload)
        if resp.status_code == 200:
            data = resp.json()
            agent_id = data.get("agentId")
            print(f"Agent registered with ID: {agent_id}")
            return agent_id
        else:
            print(f"Registration failed: {resp.status_code} - {resp.text}")
            return None
    except Exception as e:
        print(f"Registration exception: {e}")
        return None

def stream_logs(headers, agent_id):
    """Send a stream of logs"""
    print(f"Starting log stream for {AGENT_HOSTNAME} (ID: {agent_id})...")
    services = ["agent-core", "network-monitor", "compliance-scanner", "updater"]
    severities = ["INFO", "INFO", "INFO", "WARN", "ERROR"] 
    
    count = 0
    try:
        # Simulate log stream
        while True:
            # 1. Poll for instructions
            try:
                instr_resp = requests.get(f"{BASE_URL}/api/agents/{AGENT_HOSTNAME}/instructions", headers=headers)
                if instr_resp.status_code == 200:
                    instructions = instr_resp.json()
                    for instr in instructions:
                        print(f"Received instruction: {instr['type']} ({instr['id']})")
                        if instr['type'] == 'collect_evidence':
                             # Execute compliance scan
                             framework_id = instr.get("instruction", {}).get("framework_id") or "nistcsf" # Handle varying payload structures
                             # Actually payload is in top level in DB but instruction endpoint maps it? 
                             # Let's check agent_instruction_endpoints.py mapping.
                             # It maps 'instruction' field. In compliance_api we set 'payload' but maybe not 'instruction'?
                             # In compliance_api: "payload": {...}
                             # In agent_instruction_endpoints: "instruction": instr.get("instruction")
                             # Wait, I might have missed mapping 'payload' in agent_instruction_api.
                             # Let's assume the agent can read raw 'instruction' or I need to fix backend mapping.
                             # CHECK: generic structure is better.
                             # For now, let's just use a default or try to parse.
                             run_compliance_scan(headers, instr, agent_id)
            except Exception as e:
                print(f"Polling error: {e}")

            # 2. Send logs
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "severity": random.choice(severities),
                "service": random.choice(services),
                "message": f"Operation {uuid.uuid4().hex[:8]} completed",
                "hostname": AGENT_HOSTNAME, # Explicitly send hostname
                "agent_id": agent_id
            }
            
            try:
                requests.post(f"{BASE_URL}/api/logs", json=log_entry, headers=headers)
            except:
                pass
                
            count += 1
            if count % 10 == 0:
                print(f"Sent {count} logs... Last: {log_entry['message']}")
                
            time.sleep(5) # Poll every 5 seconds
    except KeyboardInterrupt:
        print("\nStopping simulation.")

def run_compliance_scan(headers, instruction, agent_id):
    print("Running Compliance Scan...")
    time.sleep(2) # Simulate work
    
    # Mock findings based on framework
    findings = []
    
    # Common controls
    controls = [
        {"id": "AC-1", "name": "Access Control Policy", "compliant": True},
        {"id": "AC-2", "name": "Account Management", "compliant": False, "reason": "Inactive accounts not disabled after 90 days", "remediation": "Configure automated account disablement script"},
        {"id": "AU-2", "name": "Audit Events", "compliant": True},
        {"id": "SC-7", "name": "Boundary Protection", "compliant": False, "reason": "Firewall rules permit inbound HTTP on non-web servers", "remediation": "Restrict inbound port 80/443 to load balancers only"},
        {"id": "SI-2", "name": "Flaw Remediation", "compliant": True},
        {"id": "CP-9", "name": "Information System Backup", "compliant": False, "reason": "Backup verification failed for last 3 cycles", "remediation": "Investigate backup agent logs and re-run full backup"}
    ]
    
    # Randomize slightly
    for c in controls:
        is_compliant = c["compliant"]
        # 20% chance to flip status to make it dynamic
        if random.random() < 0.2:
            is_compliant = not is_compliant
            
        status = "Compliant" if is_compliant else "Non-Compliant"
        
        control_data = {
            "id": c["id"],
            "status": status,
            "evidence": []
        }
        
        if not is_compliant:
            control_data["reason"] = c.get("reason", "Configuration deviates from policy")
            control_data["remediation"] = c.get("remediation", "Apply remediation playbook")
        else:
            control_data["evidence"].append({
                "name": f"Config_Dump_{c['id']}.json",
                "content": "{\"policy_check\": \"passed\", \"timestamp\": \"2023-10-27\"}",
                "data": {"checked": True}
            })
            
        findings.append(control_data)
        
    payload = {
        "agent_id": agent_id, # or AGENT_HOSTNAME 
        "framework_id": "nistcsf", # hardcoded for demo or extract from instr
        "controls": findings
    }
    
    try:
        print(f"Submitting results to backend...")
        res = requests.post(f"{BASE_URL}/api/compliance-automation/submit-agent-results", json=payload, headers=headers)
        print(f"Result submission: {res.status_code}")
    except Exception as e:
        print(f"Error submitting results: {e}")

if __name__ == "__main__":
    headers = login()
    if headers:
        agent_id = register_agent(headers)
        if agent_id:
            stream_logs(headers, agent_id)
        else:
            # Fallback for testing if registration fails but we want to stream by hostname
            print("Registration failed, streaming with hostname only (legacy mode)...")
            stream_logs(headers, None)
