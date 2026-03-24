import requests
import json

# Test login endpoint
response = requests.post(
    'http://localhost:5000/api/auth/login',
    json={
        'email': 'super@omni.ai',
        'password': 'password123'
    }
)

print("Status Code:", response.status_code)
print("\nResponse:")
data = response.json()
print(json.dumps(data, indent=2))

# Check if permissions are included
if data.get('success'):
    user = data.get('user', {})
    permissions = user.get('permissions', [])
    print(f"\n✓ Login successful!")
    print(f"✓ User role: {user.get('role')}")
    print(f"✓ Permissions count: {len(permissions)}")
    print(f"✓ Has 'view:agents': {'view:agents' in permissions}")
    print(f"✓ Has 'remediate:agents': {'remediate:agents' in permissions}")
else:
    print(f"\n✗ Login failed: {data.get('error')}")
