#!/usr/bin/env python3
"""
Enable compliance feature for admin@sriprasad.com user
"""
from pymongo import MongoClient

# Connect to MongoDB
client = MongoClient('mongodb://localhost:27017/')
db = client['omni_platform']

# Find the user
user = db.users.find_one({'email': 'admin@sriprasad.com'})
if not user:
    print("ERROR: User admin@sriprasad.com not found!")
    exit(1)

print(f"Found user: {user['email']}")
print(f"  Role: {user.get('role')}")
print(f"  Tenant ID: {user.get('tenant_id')}")
print(f"  Permissions: {user.get('permissions', {})}")

# Get the role
role_name = user.get('role', 'Tenant Admin')
role = db.roles.find_one({'name': role_name})

if role:
    print(f"\nFound role: {role['name']}")
    print(f"  Permissions: {role.get('permissions', [])}")
    
    # Check if view:compliance is in the role permissions
    if 'view:compliance' in role.get('permissions', []):
        print("  [OK] Role already has view:compliance permission")
    else:
        print("  [FAIL] Adding view:compliance to role permissions...")
        db.roles.update_one(
            {'name': role_name},
            {'$addToSet': {'permissions': 'view:compliance'}}
        )
        print("  [OK] Added view:compliance permission to role")

# Also update user directly for good measure
print("\nUpdating user permissions directly...")
db.users.update_one(
    {'email': 'admin@sriprasad.com'},
    {'$set': {'permissions.view:compliance': True}}
)

print("\n✅ Compliance feature enabled for admin@sriprasad.com")
print("User should now be able to access the Compliance page")
