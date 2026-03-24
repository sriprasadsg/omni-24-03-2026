#!/usr/bin/env python3
"""
Debug script to check what's happening during Super Admin login
"""
import os
import sys
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

# Connect to MongoDB
mongodb_url = os.getenv('MONGODB_URL', 'mongodb://localhost:27017')
db_name = os.getenv('MONGODB_DB_NAME', 'omni_agent')

client = MongoClient(mongodb_url)
db = client[db_name]

print("\n" + "="*60)
print("  DEBUGGING SUPER ADMIN PERMISSIONS")
print("="*60)

# Find all users
print("\n1. ALL USERS IN DATABASE:")
print("-" * 60)
users = list(db.users.find({}))
print(f"Total users: {len(users)}")
for user in users:
    print(f"\nUser:")
    print(f"  Email: {user.get('email')}")
    print(f"  Name: {user.get('name')}")
    print(f"  Role: {user.get('role')}")
    print(f"  Tenant ID: {user.get('tenantId')}")
    print(f"  Tenant Name: {user.get('tenantName')}")

# Find all roles
print("\n\n2. ALL ROLES IN DATABASE:")
print("-" * 60)
roles = list(db.roles.find({}))
print(f"Total roles: {len(roles)}")
for role in roles:
    print(f"\nRole: {role.get('name')}")
    print(f"  ID: {role.get('id')}")
    print(f"  Description: {role.get('description')}")
    print(f"  Tenant ID: {role.get('tenantId')}")
    permissions = role.get('permissions', [])
    print(f"  Total Permissions: {len(permissions)}")
    
    # Check for critical permissions
    critical_perms = ['view:agents', 'remediate:agents', 'view:dashboard']
    for perm in critical_perms:
        has_perm = perm in permissions
        symbol = "✓" if has_perm else "✗"
        print(f"    {symbol} {perm}")

# Check for specific Super Admin user
print("\n\n3. SUPER ADMIN USER CHECK:")
print("-" * 60)
super_admin_emails = ['super@omni.ai', 'admin@exafleucne.com', 'admin@testcorp.com']
for email in super_admin_emails:
    user = db.users.find_one({"email": email})
    if user:
        print(f"\n✓ Found user: {email}")
        print(f"  Role: {user.get('role')}")
        
        # Find their role permissions
        role_name = user.get('role')
        if role_name:
            role = db.roles.find_one({"name": role_name})
            if role:
                perms = role.get('permissions', [])
                print(f"  Role has {len(perms)} permissions")
                print(f"  Has 'view:agents': {('view:agents' in perms)}")
                print(f"  Has 'remediate:agents': {('remediate:agents' in perms)}")
            else:
                print(f"  ✗ Role '{role_name}' not found in database!")
    else:
        print(f"✗ User {email} not found")

print("\n\n4. DIAGNOSIS:")
print("-" * 60)
# Provide diagnosis
if len(users) == 0:
    print("⚠ NO USERS FOUND - Database needs seeding!")
elif len(roles) == 0:
    print("⚠ NO ROLES FOUND - Database needs role creation!")
else:
    # Check if any user has Super Admin role
    super_admins = [u for u in users if u.get('role') == 'Super Admin']
    if not super_admins:
        print("⚠ NO USERS WITH 'Super Admin' ROLE FOUND")
        print("  Available roles in users:", set(u.get('role') for u in users))
    else:
        print(f"✓ Found {len(super_admins)} Super Admin user(s)")
        
        # Check if Super Admin role exists
        super_admin_role = db.roles.find_one({"name": "Super Admin"})
        if not super_admin_role:
            print("✗ 'Super Admin' ROLE DEFINITION NOT FOUND IN ROLES COLLECTION")
        else:
            perms = super_admin_role.get('permissions', [])
            if 'view:agents' not in perms:
                print("✗ Super Admin role MISSING 'view:agents' permission")
            else:
                print("✓ Super Admin role has 'view:agents' permission")

print("\n" + "="*60)
