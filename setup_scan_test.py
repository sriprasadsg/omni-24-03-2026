import requests
import json
import time

BASE_URL = "http://localhost:5000"

def setup():
    timestamp = int(time.time())
    email = f"browser_test_{timestamp}@example.com"
    password = "password123"
    company = f"Browser Test Corp {timestamp}"
    
    print(f"Creating user: {email}")
    
    # Signup
    resp = requests.post(f"{BASE_URL}/api/auth/signup", json={
        "companyName": company,
        "name": "Browser Tester",
        "email": email,
        "password": password
    })
    
    if resp.status_code != 200:
        print("Signup failed:", resp.text)
        return None
        
    data = resp.json()
    token = data["access_token"]
    tenant_id = data["tenant"]["id"]
    reg_key = data["tenant"]["registrationKey"]
    
    print(f"User created. Token obtained. Tenant: {tenant_id}")
    
    # Register Agent
    print("Registering agent...")
    agent_resp = requests.post(f"{BASE_URL}/api/agents/register", json={
        "registrationKey": reg_key,
        "hostname": "browser-test-agent",
        "platform": "Linux",
        "ipAddress": "10.0.0.5"
    })
    
    if agent_resp.status_code != 200:
        print("Agent registration failed:", agent_resp.text)
        return None
        
    agent_id = agent_resp.json()["agentId"]
    print(f"Agent registered: {agent_id}")
    
    return {
        "email": email,
        "password": password,
        "agent_id": agent_id,
        "token": token
    }

def report_results(agent_id, token_unused):
    # Simulate receiving results
    print(f"Reporting mock results for agent {agent_id}...")
    results = [
        {"ip": "10.0.0.1", "mac": "AA:BB:CC:00:00:01", "hostname": "gateway", "device_type": "Router", "status": "Up"},
        {"ip": "10.0.0.50", "mac": "AA:BB:CC:00:00:50", "hostname": "web-server", "device_type": "Linux/Switch", "status": "Up"},
        {"ip": "10.0.0.100", "mac": "AA:BB:CC:00:01:00", "hostname": "office-pc", "device_type": "Windows", "status": "Up"}
    ]
    
    resp = requests.post(f"{BASE_URL}/api/agents/{agent_id}/discovery/results", json=results)
    if resp.status_code == 200:
        print("Results reported successfully.")
    else:
        print("Failed to report results:", resp.text)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        if len(sys.argv) < 3:
            print("Usage: python setup_scan_test.py report <agent_id>")
        else:
            report_results(sys.argv[2], None)
    else:
        creds = setup()
        if creds:
            with open("test_creds.json", "w") as f:
                json.dump(creds, f)
            print("Credentials saved to test_creds.json")
