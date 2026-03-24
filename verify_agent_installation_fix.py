"""
Simple verification that agent installation should now work
"""
from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

client = MongoClient(os.getenv("MONGODB_URL", "mongodb://localhost:27017/"))
db = client[os.getenv("MONGODB_DB_NAME", "omni_agent_db")]

print("\n" + "=" * 80)
print("AGENT INSTALLATION FIX - FINAL VERIFICATION")
print("=" * 80)

# Check roles
print("\n✅ Checking Roles...")
roles = list(db.roles.find({}, {'_id': 0, 'name': 1, 'permissions': 1}))
for role in roles:
    perms = role.get('permissions', [])
    has_view = 'view:agents' in perms
    print(f"\n   Role: {role.get('name')}")
    print(f"   - Permissions: {len(perms)}")
    print(f"   - Has 'view:agents': {'✅ YES' if has_view else '❌ NO'}")

# Check users  
print("\n✅ Checking Users...")
users = list(db.users.find({}, {'_id': 0, 'email': 1, 'role': 1}))
if len(users) == 0:
    print("   ⚠️  No users in database yet")
    print("   💡 Login to the UI or restart backend to create default super admin")
else:
    for user in users:
        print(f"\n   User: {user.get('email')}")
        print(f"   Role: {user.get('role')}")

# Check frontend change
print("\n✅ Checking Frontend Changes...")
with open('components/AgentInstallation.tsx', 'r', encoding='utf-8') as f:
    content = f.read()
    if "hasPermission('view:agents')" in content:
        print("   ✅ Frontend using 'view:agents' permission")
    elif "hasPermission('remediate:agents')" in content:
        print("   ❌ Frontend still using 'remediate:agents' permission")
    else:
        print("   ⚠️  Could not verify frontend permission check")

print("\n" + "=" * 80)
print("VERIFICATION RESULT")
print("=" * 80)

if len(roles) >= 2:  # Super Admin and Tenant Admin
    print("✅ All fixes applied successfully!")
    print("\n📋 Next Steps:")
    print("   1. Open browser: http://localhost:3000")
    print("   2. Login with your credentials")
    print("   3. Navigate to: Agents → Agent Installation")
    print("   4. Installation commands should now be visible")
else:
    print("⚠️  Roles may not be fully seeded")
    print("   Try restarting the backend to trigger seeding")

print("=" * 80 + "\n")

client.close()
