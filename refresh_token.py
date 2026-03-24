import requests
import yaml
import os

base_url = "http://localhost:5000/api/auth"

# Login
login_data = {
    "email": "admin@exafleucne.com",
    "password": "password123"
}

print("Logging in as admin@exafleucne.com...")
res = requests.post(f"{base_url}/login", json=login_data)
print(f"Status: {res.status_code}")

if res.status_code == 200:
    data = res.json()
    if data.get("success"):
        token = data.get("access_token")
        user = data.get("user", {})
        tenant_id = user.get("tenantId")
        
        print(f"✅ Login successful!")
        print(f"  User: {user.get('email')} / {user.get('username')}")
        print(f"  Tenant ID: {tenant_id}")
        print(f"  Role: {user.get('role')}")
        print(f"  Token (first 20 chars): {token[:20]}...")
        
        # Update config
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
        print("✅ Config updated in agent/config.yaml")
        
        # Verify by calling /api/auth/me
        print("\nVerifying with /api/auth/me...")
        headers = {"Authorization": f"Bearer {token}"}
        res_me = requests.get("http://localhost:5000/api/auth/me", headers=headers)
        if res_me.status_code == 200:
            me_data = res_me.json()
            print(f"  ✅ Verified! tenantId from /me: {me_data.get('tenantId')}")
        else:
            print(f"  ❌ Verification failed: {res_me.status_code}")
    else:
        print(f"Login failed: {data}")
else:
    print(f"Login failed with status {res.status_code}: {res.text}")
