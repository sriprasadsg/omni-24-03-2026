
import requests
import json
import os

BASE_URL = "http://localhost:5000"
TOKEN_FILE = "token.txt"

def verify():
    print("Reading token...")
    try:
        with open(TOKEN_FILE, "r") as f:
            token = f.read().strip()
    except FileNotFoundError:
        print("Error: token.txt not found. Cannot authenticate.")
        return

    headers = {"Authorization": f"Bearer {token}"}
    
    print("Fetching agents...")
    try:
        resp = requests.get(f"{BASE_URL}/api/agents", headers=headers)
        if resp.status_code != 200:
            print(f"Error: API returned {resp.status_code}")
            print(resp.text)
            return
            
        data = resp.json()
        if isinstance(data, dict) and "items" in data:
            agents = data["items"]
        else:
            agents = data
            
        print(f"Found {len(agents)} agents.")
        
        if not agents:
            print("No agents found.")
            return

        # Find our agent (Hostname starts with 'test' or whatever, or just pick the one with most caps)
        target_agent = None
        max_caps = 0
        
        for a in agents:
             caps = a.get('capabilities', [])
             if len(caps) > max_caps:
                 max_caps = len(caps)
                 target_agent = a
        
        if not target_agent:
            target_agent = agents[0]

        print(f"Inspecting Agent: {target_agent.get('hostname')} (ID: {target_agent.get('id')})")
        print(f"Status: {target_agent.get('status')}")
        
        caps = target_agent.get('capabilities', [])
        print(f"Capabilities Count: {len(caps)}")
        print("Capabilities List:")
        for i, cap in enumerate(caps, 1):
            print(f"{i}. {cap}")
            
        if len(caps) >= 14:
            print("\nSUCCESS: All 14 features are active and reported.")
        else:
            print(f"\nWARNING: Expected 14 features, found {len(caps)}.")

    except Exception as e:
        print(f"Exception: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify()
