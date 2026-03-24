import requests
import yaml
import json

try:
    with open("agent/config.yaml", "r") as f:
        config = yaml.safe_load(f)

    base_url = config["api_base_url"]
    token = config["agent_token"]
    
    headers = {"Authorization": f"Bearer {token}"}
    
    print("--- Debug: Checking User ---")
    res = requests.get(f"{base_url}/api/auth/me", headers=headers)
    print(f"Me: {res.text}")
    
    print("\n--- Debug: Checking Agents ---")
    res = requests.get(f"{base_url}/api/agents", headers=headers)
    print(f"Agents Status: {res.status_code}")
    print(f"Agents Body: {res.text}")

except Exception as e:
    print(f"Error: {e}")
