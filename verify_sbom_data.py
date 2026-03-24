import requests
import yaml
import json

# Load config to get token
try:
    with open("agent/config.yaml", "r") as f:
        config = yaml.safe_load(f)
    token = config["agent_token"]
    print(f"Using Token: {token[:10]}...")
except:
    print("Could not load agent/config.yaml for token. Run onboard.py first.")
    exit(1)

base_url = "http://localhost:5000/api/sboms"
headers = {"Authorization": f"Bearer {token}"}

print("\n--- Checking SBOMs List ---")
try:
    res = requests.get(base_url, headers=headers)
    print(f"Status: {res.status_code}")
    if res.status_code == 200:
        data = res.json()
        print(f"Count: {len(data)}")
        print(json.dumps(data, indent=2))
    else:
        print(res.text)
except Exception as e:
    print(f"Error: {e}")

print("\n--- Checking Components ---")
try:
    res = requests.get(f"{base_url}/components", headers=headers)
    print(f"Status: {res.status_code}")
    if res.status_code == 200:
        data = res.json()
        print(f"Count: {len(data)}")
        # Print first 2 components only to avoid spam
        print(json.dumps(data[:2], indent=2)) 
    else:
        print(res.text)
except Exception as e:
    print(f"Error: {e}")
