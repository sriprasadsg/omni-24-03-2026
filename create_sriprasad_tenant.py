"""
Clean MongoDB and create fresh sriprasad tenant
"""
from pymongo import MongoClient
import requests
import json

# Connect to MongoDB
client = MongoClient('mongodb://localhost:27017')
db = client['omni_platform']

print("🗑️  Cleaning MongoDB database...")

# Delete all tenant-related data
collections_to_clean = [
    'tenants',
    'users',
    'agents',
    'assets',
    'security_events',
    'security_cases',
    'audit_logs',
    'notifications',
    'threat_intelligence',
    'vulnerabilities',
    'patches',
    'cloud_accounts',
    'cspm_findings'
]

for collection_name in collections_to_clean:
    result = db[collection_name].delete_many({})
    print(f"   Deleted {result.deleted_count} documents from {collection_name}")

print("\n✅ Database cleaned successfully!")

# Create sriprasad tenant
print("\n🏢 Creating sriprasad tenant...")

tenant_data = {
    "companyName": "sriprasad",
    "name": "Sri Prasad Admin",
    "email": "admin@sriprasad.com",
    "password": "SriPrasad123!"
}

try:
    response = requests.post(
        "http://localhost:5000/api/auth/signup",
        json=tenant_data,
        timeout=10
    )
    
    if response.status_code == 200:
        result = response.json()
        if result.get('success'):
            print("✅ sriprasad tenant created successfully!\n")
            print(f"Tenant ID: {result['tenant']['id']}")
            print(f"Tenant Name: {result['tenant']['name']}")
            print(f"Registration Key: {result['tenant']['registrationKey']}\n")
            print(f"Admin Email: {result['user']['email']}")
            print(f"Admin Name: {result['user']['name']}")
            print(f"Admin Role: {result['user']['role']}\n")
            
            # Save tenant ID for agent configuration
            with open('sriprasad_tenant_id.txt', 'w') as f:
                f.write(result['tenant']['id'])
            print(f"📝 Tenant ID saved to: sriprasad_tenant_id.txt\n")
            
            print("="*60)
            print("LOGIN CREDENTIALS:")
            print("="*60)
            print(f"URL: http://localhost:3000")
            print(f"Email: {tenant_data['email']}")
            print(f"Password: {tenant_data['password']}")
            print("="*60)
            
        else:
            print(f"❌ Error: {result.get('error', 'Unknown error')}")
    else:
        print(f"❌ HTTP Error {response.status_code}")
        print(f"Response: {response.text}")
        
except requests.exceptions.ConnectionError:
    print("❌ Cannot connect to backend API at http://localhost:5000")
    print("Please ensure the backend is running")
except Exception as e:
    print(f"❌ Error: {e}")

print("\n✨ Done!")
