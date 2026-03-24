"""
Test if agent installation is accessible with current permissions
"""
import requests
import yaml

# Load token from config
with open('agent/config.yaml', 'r') as f:
    config = yaml.safe_load(f)
    token = config.get('agent_token')

if not token:
    print("❌ No token found in agent/config.yaml")
    exit(1)

headers = {
    'Authorization': f'Bearer {token}',
    'Content-Type': 'application/json'
}

print("=" * 70)
print("TESTING AGENT INSTALLATION ACCESS")
print("=" * 70)

# Test 1: Check current user info
print("\n[1/3] Checking current user authentication...")
try:
    response = requests.get('http://localhost:5000/api/auth/me', headers=headers)
    if response.status_code == 200:
        user_data = response.json()
        print(f"   ✅ Authenticated as: {user_data.get('email')}")
        print(f"      Role: {user_data.get('role')}")
        print(f"      Tenant: {user_data.get('tenantName')} ({user_data.get('tenantId')})")
    else:
        print(f"   ❌ Authentication failed: {response.status_code}")
        print(f"      {response.text}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 2: Get tenant registration key (needed for agent installation)
print("\n[2/3] Fetching tenant registration key...")
try:
    response = requests.get('http://localhost:5000/api/tenants', headers=headers)
    if response.status_code == 200:
        tenants = response.json()
        if tenants:
            tenant = tenants[0]
            reg_key = tenant.get('registrationKey')
            print(f"   ✅ Tenant: {tenant.get('name')}")
            print(f"      Registration Key: {reg_key[:20]}..." if reg_key else "      ❌ No registration key")
        else:
            print("   ⚠️  No tenants found")
    else:
        print(f"   ❌ Failed: {response.status_code}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 3: Check if agents endpoint is accessible
print("\n[3/3] Testing agents endpoint access...")
try:
    response = requests.get('http://localhost:5000/api/agents', headers=headers)
    if response.status_code == 200:
        agents = response.json()
        print(f"   ✅ Agents endpoint accessible")
        print(f"      Found {len(agents)} agent(s)")
    elif response.status_code == 403:
        print(f"   ❌ Access denied (403) - Missing 'view:agents' permission")
    else:
        print(f"   ⚠️  Status: {response.status_code}")
except Exception as e:
    print(f"   ❌ Error: {e}")

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print("If all tests passed, agent installation should be accessible in the UI.")
print("Navigate to: http://localhost:3000 → Agents → Agent Installation")
print("=" * 70)
