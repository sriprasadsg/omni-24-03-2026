"""
Diagnose login issues - check database and test authentication
"""
from pymongo import MongoClient
import bcrypt

import os

def verify_password(plain_password, hashed_password):
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

# Connect to MongoDB
MONGO_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGODB_DB_NAME", "omni_platform")

client = MongoClient(MONGO_URL)
db = client[DB_NAME]

print("🔍 DIAGNOSING LOGIN ISSUES\n")
print(f"📡 Connecting to {MONGO_URL}...")
print("="*60)

# Check tenants
print("\n📊 TENANTS IN DATABASE:")
tenants = list(db.tenants.find({}))
if tenants:
    for tenant in tenants:
        print(f"\n  ✅ {tenant.get('name')}")
        print(f"     ID: {tenant.get('id')}")
else:
    print("  ❌ NO TENANTS FOUND!")

# Check users
print("\n\n👤 USERS IN DATABASE:")
users = list(db.users.find({}))
if users:
    for user in users:
        print(f"\n  Email: {user.get('email')}")
        print(f"  Name: {user.get('name')}")
        print(f"  Role: {user.get('role')}")
        print(f"  Tenant: {user.get('tenantId')}")
        print(f"  Password Hash: {user.get('password')[:50]}...")
        
        # Test password verification
        if user.get('email') == 'super@omni.ai':
            test_pass = 'password123'
            is_valid = verify_password(test_pass, user.get('password'))
            print(f"  ✅ Password 'password123' verifies: {is_valid}")
        elif user.get('email') == 'admin@sriprasad.com':
            test_pass = 'Admin123!'
            is_valid = verify_password(test_pass, user.get('password'))
            print(f"  ✅ Password 'Admin123!' verifies: {is_valid}")
else:
    print("  ❌ NO USERS FOUND!")

print("\n" + "="*60)
print("\n📝 SUMMARY:")
print(f"   Tenants: {len(tenants)}")
print(f"   Users: {len(users)}")

if not tenants:
    print("\n⚠️  DATABASE IS EMPTY - No tenants found!")
    print("   Run: python create_super_admin.py")
    print("   Run: python 'setup_sri prasad_bcrypt.py'")
elif not users:
    print("\n⚠️  NO USERS - Tenants exist but no users!")
    print("   Run: python create_super_admin.py")
else:
    print("\n✅ Database looks OK")
    print("\n🔧 If login still fails, try:")
    print("   1. Stop backend (Ctrl+C)")
    print("   2. Restart: python -m uvicorn app:app --port 5000")
    print("   3. Try login again")
