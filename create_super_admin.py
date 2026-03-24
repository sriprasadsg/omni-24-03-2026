"""
Add Super Admin account to the platform
"""
import os
import sys
from pymongo import MongoClient
import bcrypt
import uuid
from datetime import datetime, timezone

def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

# Connect to MongoDB
MONGO_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGODB_DB_NAME", "omni_platform")

client = MongoClient(MONGO_URL)
db = client[DB_NAME]

print(f"Connecting to MongoDB at {MONGO_URL}...")
print("Creating/Verifying Super Admin account...\n")

# Create platform-admin tenant if it doesn't exist
platform_tenant_id = "platform-admin"
existing_tenant = db.tenants.find_one({"id": platform_tenant_id})

if not existing_tenant:
    tenant_doc = {
        "id": platform_tenant_id,
        "name": "Platform Administration",
        "subscriptionTier": "Enterprise",
        "registrationKey": f"reg_{uuid.uuid4().hex[:16]}",
        "apiKeys": [],
        "enabledFeatures": ["*"],  # All features enabled
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "updatedAt": datetime.now(timezone.utc).isoformat()
    }
    db.tenants.insert_one(tenant_doc)
    print(f"✅ Platform-admin tenant created: {platform_tenant_id}")
else:
    print(f"ℹ Platform-admin tenant already exists: {platform_tenant_id}")

# Check if super admin already exists
existing_super = db.users.find_one({"email": "super@omni.ai"})

if existing_super:
    print("ℹ Super admin already exists!")
    print(f"   Email: {existing_super.get('email')}")
    print(f"   Name: {existing_super.get('name')}")
    
    # Update password to ensure it works
    password = "password123"
    hashed_password = get_password_hash(password)
    
    db.users.update_one(
        {"email": "super@omni.ai"},
        {"$set": {
            "password": hashed_password,
            "updatedAt": datetime.now(timezone.utc).isoformat()
        }}
    )
    print(f"✅ Password reset to 'password123' for verification")
else:
    # Create super admin user
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    password = "password123"
    hashed_password = get_password_hash(password)

    user_doc = {
        "id": user_id,
        "email": "super@omni.ai",
        "password": hashed_password,
        "name": "Super Admin",
        "role": "Super Admin",
        "tenantId": platform_tenant_id,
        "avatar": "",
        "status": "Active",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "updatedAt": datetime.now(timezone.utc).isoformat()
    }

    db.users.insert_one(user_doc)
    print(f"✅ Super Admin created: {user_id}")

# Save credentials
with open('super_admin_credentials.txt', 'w') as f:
    f.write("SUPER ADMIN CREDENTIALS\n")
    f.write("="*40 + "\n")
    f.write(f"Email: super@omni.ai\n")
    f.write(f"Password: password123\n")
    f.write(f"Role: Super Admin\n")
    f.write(f"Tenant: {platform_tenant_id}\n")
    f.write("="*40 + "\n")
    f.write("\nSuper Admin has access to:\n")
    f.write("- All tenants\n")
    f.write("- Tenant management\n")
    f.write("- All platform features\n")
    f.write("- System-wide administration\n")

print("\n" + "="*60)
print("🚀 SUPER ADMIN ACCOUNT READY")
print("="*60)
print("Email: super@omni.ai")
print("Password: password123")
print("Role: Super Admin")
print("Access: Platform-wide (all tenants)")
print("="*60)
print("\n✅ Credentials saved to: super_admin_credentials.txt")
print("✅ Login at: http://localhost:3000")
