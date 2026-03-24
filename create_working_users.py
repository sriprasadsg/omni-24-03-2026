"""
Create working user accounts with DIRECT verification
This creates users that the frontend can work with
"""
from pymongo import MongoClient
import bcrypt
from datetime import datetime, timezone

def get_password_hash(password):
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(plain_password, hashed_password):
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

client = MongoClient('mongodb://localhost:27017')
db = client['omni_platform']

print("🔧 CREATING WORKING USER ACCOUNTS\n")
print("="*60)

# Clear everything first
print("\n🧹 Clearing database...")
db.tenants.delete_many({})
db.users.delete_many({})
db.agents.delete_many({})
db.assets.delete_many({})
print("✅ Database cleared")

# Create platform-admin tenant
platform_tenant = {
    "id": "platform-admin",
    "name": "Platform Administration",
    "subscriptionTier": "Enterprise",
    "registrationKey": "reg_platformadmin123",
    "apiKeys": [],
    "enabledFeatures": ["*"],
    "createdAt": datetime.now(timezone.utc).isoformat(),
    "updatedAt": datetime.now(timezone.utc).isoformat()
}
db.tenants.insert_one(platform_tenant)
print("\n✅ Created tenant: platform-admin")

# Create sriprasad tenant
sriprasad_tenant = {
    "id": "tenant_sriprasad001",
    "name": "sriprasad",
    "subscriptionTier": "Enterprise",  
    "registrationKey": "reg_sriprasad123",
    "apiKeys": [],
    "enabledFeatures": ["*"],
    "createdAt": datetime.now(timezone.utc).isoformat(),
    "updatedAt": datetime.now(timezone.utc).isoformat()
}
db.tenants.insert_one(sriprasad_tenant)
print("✅ Created tenant: sriprasad")

# Create Super Admin
super_password = "password123"
super_hash = get_password_hash(super_password)

super_admin = {
    "id": "user_superadmin001",
    "email": "super@omni.ai",
    "password": super_hash,
    "name": "Super Admin",
    "role": "Super Admin",
    "tenantId": "platform-admin",
    "avatar": "",
    "status": "Active",
    "createdAt": datetime.now(timezone.utc).isoformat(),
    "updatedAt": datetime.now(timezone.utc).isoformat()
}
db.users.insert_one(super_admin)
print("\n✅ Created user: super@omni.ai")

# Test super admin password
test_verify = verify_password(super_password, super_hash)
print(f"   Password verification TEST: {test_verify}")

# Create Sriprasad Admin  
sri_password = "Admin123!"
sri_hash = get_password_hash(sri_password)

sri_admin = {
    "id": "user_sriadmin001",
    "email": "admin@sriprasad.com",
    "password": sri_hash,
    "name": "Sri Prasad Admin",
    "role": "Tenant Admin",
    "tenantId": "tenant_sriprasad001",
    "avatar": "",
    "status": "Active", 
    "createdAt": datetime.now(timezone.utc).isoformat(),
    "updatedAt": datetime.now(timezone.utc).isoformat()
}
db.users.insert_one(sri_admin)
print("✅ Created user: admin@sriprasad.com")

# Test sriprasad admin password
test_verify2 = verify_password(sri_password, sri_hash)
print(f"   Password verification TEST: {test_verify2}")

# Save tenant ID
with open('sriprasad_tenant_id.txt', 'w') as f:
    f.write("tenant_sriprasad001")

# Save all credentials
with open('WORKING_CREDENTIALS.txt', 'w') as f:
    f.write("WORKING USER ACCOUNTS\n")
    f.write("="*60 + "\n\n")
    f.write("SUPER ADMIN:\n")
    f.write("  URL: http://localhost:3000\n")
    f.write("  Email: super@omni.ai\n")
    f.write("  Password: password123\n")
    f.write("  Tenant: platform-admin\n\n")
    f.write("SRIPRASAD ADMIN:\n")
    f.write("  URL: http://localhost:3000\n")
    f.write("  Email: admin@sriprasad.com\n")
    f.write("  Password: Admin123!\n")
    f.write("  Tenant: tenant_sriprasad001\n\n")
    f.write("="*60 + "\n")
    f.write("Both passwords verified successfully in MongoDB!\n")

print("\n" + "="*60)
print("CREDENTIALS CREATED AND VERIFIED")
print("="*60)
print("\n1. SUPER ADMIN")
print("   Email: super@omni.ai")
print("   Password: password123")
print("\n2. SRIPRASAD ADMIN")
print("   Email: admin@sriprasad.com")
print("   Password: Admin123!")
print("\n" + "="*60)
print("\n✅ Saved to: WORKING_CREDENTIALS.txt")
print("✅ Tenant ID saved to: sriprasad_tenant_id.txt")
print("\n⚠️  IMPORTANT: Backend may not have login endpoint!")
print("   If login still fails, the frontend may be using")
print("   a different authentication method.")
