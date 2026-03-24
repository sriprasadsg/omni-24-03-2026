import requests
import time
import sys
import json

BASE_URL = "http://localhost:5000"


TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbkBleGFmbHVlbmNlLmNvbSIsInJvbGUiOiJUZW5hbnQgQWRtaW4iLCJ0ZW5hbnRfaWQiOiJ0ZW5hbnRfODJkZGEwZjMzYmM0IiwiZXhwIjoxODAxNjkwNjQ1fQ.SJv2EXw-5-BXJQTVpx2C-8h7p_xCpOMxNf0LJraufvU"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

def get_agents():
    try:
        resp = requests.get(f"{BASE_URL}/api/agents", headers=HEADERS)
        resp.raise_for_status()
        return resp.json().get('items', [])
    except Exception as e:
        print(f"Error getting agents: {e}")
        try:
             print(f"Response: {resp.text}")
        except: pass
        return []

def trigger_scan(agent_id):
    try:
        resp = requests.post(f"{BASE_URL}/api/agents/{agent_id}/compliance/scan")
        resp.raise_for_status()
        print(f"Triggered scan for agent {agent_id}: {resp.json()}")
        return True
    except Exception as e:
        print(f"Error triggering scan: {e}")
        return False

def check_evidence(hostname):
    asset_id = f"asset-{hostname}"
    try:
        resp = requests.get(f"{BASE_URL}/api/assets/{asset_id}/compliance", headers=HEADERS)
        resp.raise_for_status()
        data = resp.json()
        
        found_cloud = False
        found_pii = False
        
        # data is a list of compliance records
        # each record has 'checkName'
        
        # print(f"DEBUG: Found {len(data)} compliance records for {asset_id}")
        
        for record in data:
            check_name = record.get('checkName')
            # print(f"  - {check_name}")
            if check_name == "Cloud Instance Metadata":
                found_cloud = True
            if check_name == "PII Data Discovery":
                found_pii = True
                
        return found_cloud, found_pii
    except Exception as e:
        print(f"Error checking evidence: {e}")
        return False, False

def main():
    print("1. Getting agents...")
    agents = get_agents()
    if not agents:
        print("No agents found.")
        sys.exit(1)
        
    # Prefer online agent
    target_agent = next((a for a in agents if a.get('status') == 'Online'), agents[0])
    agent_id = target_agent.get('id')
    hostname = target_agent.get('hostname')
    
    print(f"Target Agent: {agent_id} ({hostname})")
    
    if not trigger_scan(agent_id):
        sys.exit(1)
        
    print("2. Polling for evidence (timeout 60s)...")
    for i in range(12):
        cloud, pii = check_evidence(hostname)
        print(f"Attempt {i+1}: Cloud={cloud}, PII={pii}")
        
        if cloud and pii:
            print("SUCCESS: Both Cloud Metadata and PII Discovery evidence found!")
            sys.exit(0)
            
        time.sleep(5)
        
    print("TIMEOUT: Evidence not found.")
    sys.exit(1)

if __name__ == "__main__":
    main()
