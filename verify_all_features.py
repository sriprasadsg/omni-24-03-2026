import requests
import json
import time
import sys
from datetime import datetime

BASE_URL = "http://127.0.0.1:5000"
API_BASE = f"{BASE_URL}/api"
USERNAME = "super@omni.ai"
PASSWORD = "password123"

def print_header(title):
    print(f"\n{'='*80}")
    print(f"TESTING: {title}")
    print(f"{'='*80}")

def print_result(name, success, details=""):
    status = "✅ PASS" if success else "❌ FAIL"
    print(f"{status} - {name} {details}")

def login():
    try:
        # Use correct endpoint and JSON payload as seen in simulate_agent_activity.py
        print(f"Logging in to {API_BASE}/auth/login...")
        response = requests.post(f"{API_BASE}/auth/login", json={
            "email": USERNAME,  # API expects 'email', not 'username'
            "password": PASSWORD
        })
        if response.status_code == 200:
            token = response.json()["access_token"]
            print_result("Authentication", True, f"Token obtained for {USERNAME}")
            return {"Authorization": f"Bearer {token}"}
        else:
            print_result("Authentication", False, f"Status: {response.status_code}\nResponse: {response.text}")
            sys.exit(1)
    except Exception as e:
        print_result("Authentication", False, f"Exception: {str(e)}")
        sys.exit(1)

def test_agents(headers):
    print_header("AGENT MANAGEMENT")
    try:
        res = requests.get(f"{API_BASE}/agents", headers=headers)
        if res.status_code == 200:
            agents = res.json()
            print_result("List Agents", True, f"Found {len(agents)} agents")
            for agent in agents[:3]:
                print(f"   - {agent.get('hostname')} ({agent.get('status')}) ID: {agent.get('id')}")
        else:
            print_result("List Agents", False, f"Status: {res.status_code}\nResponse: {res.text}")
    except Exception as e:
        print_result("List Agents", False, str(e))

def test_logs(headers):
    print_header("LOGGING & OBSERVABILITY")
    try:
        # Ingest Log
        log_entry = {
            "severity": "INFO",
            "service": "feature-verifier",
            "hostname": "test-runner",
            "message": f"Verification run at {datetime.now().isoformat()}",
            "agentId": "verifier-01"
        }
        res = requests.post(f"{API_BASE}/logs", headers=headers, json=log_entry)
        if res.status_code == 200:
            print_result("Log Ingestion", True, "Log accepted")
        else:
            print_result("Log Ingestion", False, f"Status: {res.status_code}\nResponse: {res.text}")

        # Fetch Logs
        res = requests.get(f"{API_BASE}/logs", headers=headers)
        if res.status_code == 200:
            logs = res.json()
            if isinstance(logs, list):
                print_result("Fetch Logs", True, f"Retrieved {len(logs)} logs")
                found = any(l.get('service') == 'feature-verifier' for l in logs[:50])
                print_result("Log Persistence", found, "Found recently ingested log")
            else:
                 print_result("Fetch Logs", False, f"Unexpected format: {type(logs)}\nData: {str(logs)[:100]}...")
        else:
            print_result("Fetch Logs", False, f"Status: {res.status_code}\nResponse: {res.text}")
    except Exception as e:
        print_result("Log Tests", False, str(e))

def test_security(headers):
    print_header("SECURITY MODULES")
    # Based on file structure: 
    # vulnerability_endpoints.py -> /api/vulnerabilities
    # patch_endpoints.py -> /api/patches
    # compliance_framework_endpoints.py -> /api/compliance/frameworks
    endpoints = [
        ("Vulnerabilities", "/vulnerabilities"), 
        ("Patches", "/patches"),
        ("Compliance Oracle", "/compliance_oracle/compliance-status") # Guessing endpoint
    ]
    
    for name, endpoint in endpoints:
        try:
            res = requests.get(f"{API_BASE}{endpoint}", headers=headers)
            if res.status_code == 200:
                data = res.json()
                count = len(data) if isinstance(data, list) else "N/A"
                print_result(f"Fetch {name}", True, f"Count: {count}")
            else:
                # 404 is expected if I guessed wrong, but we want to know
                print_result(f"Fetch {name}", False, f"Status: {res.status_code}")
        except Exception as e:
            print_result(f"Fetch {name}", False, str(e))

def test_infrastructure(headers):
    print_header("INFRASTRUCTURE")
    endpoints = [
        ("Assets", "/assets"),
        ("Network Devices", "/network-devices"),
        ("Cloud Accounts", "/cloud-accounts")
    ]
    for name, endpoint in endpoints:
        try:
            res = requests.get(f"{API_BASE}{endpoint}", headers=headers)
            if res.status_code == 200:
                print_result(f"Fetch {name}", True)
            else:
                print_result(f"Fetch {name}", False, f"Status: {res.status_code}")
        except:
             print_result(f"Fetch {name}", False, "Connection Error")

def main():
    print(f"Starting Comprehensive Feature Verification against {BASE_URL}...")
    headers = login()
    test_agents(headers)
    test_logs(headers)
    test_security(headers)
    test_infrastructure(headers)
    print("\nVerification Complete.")

if __name__ == "__main__":
    main()
