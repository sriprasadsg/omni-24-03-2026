"""
Check what's in the MongoDB database
"""
from pymongo import MongoClient
import json

client = MongoClient('mongodb://localhost:27017')
db = client['omni_platform']

print("="*60)
print("MONGODB DATABASE STATUS")
print("="*60)

# Check tenants
print("\n📊 TENANTS:")
tenants = list(db.tenants.find({}))
if tenants:
    for tenant in tenants:
        print(f"\n  ID: {tenant.get('id')}")
        print(f"  Name: {tenant.get('name')}")
        print(f"  Registration Key: {tenant.get('registrationKey', 'N/A')}")
else:
    print("  No tenants found!")

# Check users
print("\n👤 USERS:")
users = list(db.users.find({}))
if users:
    for user in users:
        print(f"\n  Email: {user.get('email')}")
        print(f"  Name: {user.get('name')}")
        print(f"  Role: {user.get('role')}")
        print(f"  Tenant ID: {user.get('tenantId')}")
        print(f"  Has Password: {'Yes' if user.get('password') else 'No'}")
else:
    print("  No users found!")

# Check indexes
print("\n🔍 INDEXES:")
print("  Tenants collection indexes:")
for index in db.tenants.list_indexes():
    print(f"    - {index}")

print("\n" + "="*60)
