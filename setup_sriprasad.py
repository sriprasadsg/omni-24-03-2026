"""
Create sriprasad tenant directly in MongoDB with proper password hashing
"""
from pymongo import MongoClient
import hashlib
import uuid
from datetime import datetime, timezone

def hash_password(password: str) -> str:
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

# Connect to MongoDB
client = MongoClient('mongodb://localhost:27017')
db = client['omni_platform']

print("🧹 Cleaning database...")

# Clean up existing data
db.tenants.delete_many({})
db.users.delete_many({})
db.agents.delete_many({})
db.assets.delete_many({})
db.security_events.delete_many({})
db.threat_intelligence.delete_many({})

print("✅ Database cleaned")

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
print(f"\n✅ Tenant created: {tenant_id}")

# Create admin user
user_id = f"user_{uuid.uuid4().hex[:12]}"
password = "Admin123!"
hashed_password = hash_password(password)

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

# Save credentials
with open('sriprasad_credentials.txt', 'w') as f:
    f.write(f"Tenant ID: {tenant_id}\n")
    f.write(f"Registration Key: {registration_key}\n")
    f.write(f"Admin Email: admin@sriprasad.com\n")
    f.write(f"Admin Password: {password}\n")
    f.write(f"User ID: {user_id}\n")

print("\n" + "="*60)
print("SRIPRASAD TENANT CREATED SUCCESSFULLY")
print("="*60)
print(f"Tenant ID: {tenant_id}")
print(f"Registration Key: {registration_key}")
print("")
print("LOGIN CREDENTIALS:")
print(f"  URL: http://localhost:3000")
print(f"  Email: admin@sriprasad.com")
print(f"  Password: {password}")
print("="*60)
print("\n✅ Credentials saved to: sriprasad_credentials.txt")
