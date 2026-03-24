import requests
import yaml
import json
import os

base_url = "http://localhost:5000/api/auth"

# Signup
signup_data = {
    "companyName": "Exafleucne", 
    "name": "Admin Exa", 
    "email": "admin@exafleucne.com", 
    "password": "password123"
}

# Check if already signed up (Login first)
login_data = {
    "email": "admin@exafleucne.com", 
    "password": "password123"
}

print("Attempting to Login first...")
try:
    res = requests.post(f"{base_url}/login", json=login_data)
    if res.status_code == 200 and res.json().get("success"):
        print("User already exists. Skipping signup.")
    else:
        print("Signing up...")
        res = requests.post(f"{base_url}/signup", json=signup_data)
        print(f"Signup Status: {res.status_code}")
        print(f"Signup Response: {res.text}")
except Exception as e:
    print(f"Error accessing API: {e}")
    exit(1)

# Login to get fresh token
print("Logging in...")
res = requests.post(f"{base_url}/login", json=login_data)
print(f"Login Status: {res.status_code}")

if res.status_code == 200:
    data = res.json()
    if data.get("success"):
        token = data.get("access_token")
        tenant_id = data.get("user", {}).get("tenantId")
        print(f"TOKEN: {token}")
        print(f"TENANT_ID: {tenant_id}")
        
        # Write config
        config = {
            "api_base_url": "http://localhost:5000",
            "tenant_id": tenant_id,
            "agent_token": token,
            "agentic_mode_enabled": False
        }
        
        # Ensure agent dir exists
        if not os.path.exists("agent"):
            os.makedirs("agent")
            
        with open("agent/config.yaml", "w") as f:
            yaml.dump(config, f)
        print("Config written to agent/config.yaml")
    else:
         print(f"Login Failed: {data}")
else:
    print(f"Login Failed with status {res.status_code}: {res.text}")
