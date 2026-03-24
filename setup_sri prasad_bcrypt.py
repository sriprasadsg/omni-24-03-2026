"""
Create sriprasad tenant with CORRECT bcrypt password hashing
"""
from pymongo import MongoClient
import bcrypt

def get_password_hash(password):
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

# Connect to MongoDB
client = MongoClient('mongodb://localhost:27017')
db = client['omni_platform']

print("🧹 Cleaning database...")

# Clean all data
db.tenants.delete_many({})
db.users.delete_many({})
db.agents.delete_many({})
db.assets.delete_many({})
db.security_events.delete_many({})
db.threat_intelligence.delete_many({})

print("✅ Database cleaned\n")

# Create sriprasad tenant
tenant_id = f"tenant_{uuid.uuid4().hex[:12]}"
registration_key = f"reg_{uuid.uuid4().hex[:16]}"

tenant_doc = {
    "id": tenant_id,
    "name": "sriprasad",
    "subscriptionTier": "Enterprise",
    "registrationKey": registration_key,
    "apiKeys": [],
    "enabledFeatures": [
        "agents", "assets", "patch_management", "cloud_security",
        "security_ops", "compliance", "ai_governance", "threat_hunting",
        "automation", "devsecops", "finops", "audit_log"
    ],
    "createdAt": datetime.now(timezone.utc).isoformat(),
    "updatedAt": datetime.now(timezone.utc).isoformat()
}

db.tenants.insert_one(tenant_doc)
print(f"✅ Tenant created: {tenant_id}")

# Create admin user with BCRYPT hashed password
user_id = f"user_{uuid.uuid4().hex[:12]}"
password = "Admin123!"
hashed_password = get_password_hash(password)  # Using bcrypt!

user_doc = {
    "id": user_id,
    "email": "admin@sriprasad.com",
    "password": hashed_password,
    "name": "Sri Prasad Admin",
    "role": "Tenant Admin",
    "tenantId": tenant_id,
    "avatar": "",
    "status": "Active",
    "createdAt": datetime.now(timezone.utc).isoformat(),
    "updatedAt": datetime.now(timezone.utc).isoformat()
}

db.users.insert_one(user_doc)
print(f"✅ User created: {user_id}")
print(f"✅ Password hashed with bcrypt\n")

# Save credentials
with open('sriprasad_credentials.txt', 'w') as f:
    f.write(f"Tenant ID: {tenant_id}\n")
    f.write(f"Registration Key: {registration_key}\n")
    f.write(f"\nLOGIN CREDENTIALS:\n")
    f.write(f"URL: http://localhost:3000\n")
    f.write(f"Email: admin@sriprasad.com\n")
    f.write(f"Password: {password}\n")

# Save tenant ID for agent configuration
with open('sriprasad_tenant_id.txt', 'w') as f:
    f.write(tenant_id)

print("="*60)
print("SRIPRASAD TENANT CREATED SUCCESSFULLY")
print("="*60)
print(f"Tenant ID: {tenant_id}")
print(f"Registration Key: {registration_key}")
print("")
print("LOGIN CREDENTIALS:")
print(f"  URL: http://localhost:3000")
print(f"  Email: admin@sriprasad.com")
print(f"  Password: {password}")
print("   Role: Tenant Admin")
print("="*60)
print("\n✅ Credentials saved to: sriprasad_credentials.txt")
print("✅ Tenant ID saved to: sriprasad_tenant_id.txt")
print("\n🔥 Ready to test!")
