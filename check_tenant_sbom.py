import requests
import yaml

# Load config to get token
with open("agent/config.yaml", "r") as f:
    config = yaml.safe_load(f)
token = config["agent_token"]

base_url = "http://localhost:5000"
headers = {"Authorization": f"Bearer {token}"}

# 1. Check current user
print("=== Checking Current User ===")
try:
    res = requests.get(f"{base_url}/api/auth/me", headers=headers)
    if res.status_code == 200:
        user = res.json()
        print(f"Logged in as: {user.get('username')} / {user.get('email')}")
        print(f"Tenant ID: {user.get('tenantId')}")
        print(f"Tenant Name: {user.get('tenantName')}")
    else:
        print(f"Error: {res.status_code} - {res.text}")
except Exception as e:
    print(f"Error: {e}")

# 2. Check SBOM count
print("\n=== Checking SBOMs ===")
try:
    res = requests.get(f"{base_url}/api/sboms", headers=headers)
    if res.status_code == 200:
        sboms = res.json()
        print(f"Total SBOMs: {len(sboms)}")
        for sbom in sboms:
            print(f"  - {sbom.get('applicationName')} (ID: {sbom.get('id')})")
            print(f"    Tenant: {sbom.get('tenantId')}")
            print(f"    Component Count: {sbom.get('componentCount')}")
    else:
        print(f"Error: {res.status_code} - {res.text}")
except Exception as e:
    print(f"Error: {e}")

# 3. Check Components count
print("\n=== Checking Components ===")
try:
    res = requests.get(f"{base_url}/api/sboms/components", headers=headers)
    if res.status_code == 200:
        components = res.json()
        print(f"Total Components: {len(components)}")
        if components:
            print(f"First component: {components[0].get('name')} v{components[0].get('version')}")
            print(f"  Tenant: {components[0].get('tenantId')}")
            print(f"  Supplier: {components[0].get('supplier')}")
    else:
        print(f"Error: {res.status_code} - {res.text}")
except Exception as e:
    print(f"Error: {e}")
