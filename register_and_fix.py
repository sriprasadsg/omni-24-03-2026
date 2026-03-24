import sys
import os
import asyncio
import requests
import socket

# Setup API path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from database import connect_to_mongo, get_database

API_URL = "http://localhost:5000/api"

async def main():
    print("Connecting to DB...")
    await connect_to_mongo()
    db = get_database()
    
    # 1. Find Tenant for admin@exafluence.com
    email = "admin@exafluence.com"
    user = await db.users.find_one({"email": email})
    if not user:
        print(f"User {email} not found. Trying super@omni.ai")
        email = "super@omni.ai"
        user = await db.users.find_one({"email": email})
        
    if not user:
        print("No suitable admin user found.")
        return

    tenant_id = user["tenantId"]
    print(f"Target Tenant: {tenant_id}")
    
    tenant = await db.tenants.find_one({"id": tenant_id})
    if not tenant:
        print("Tenant doc not found! Creating it...")
        # Create missing tenant
        import uuid
        reg_key = f"key_{uuid.uuid4().hex[:12]}"
        new_tenant = {
            "id": tenant_id,
            "name": "Exafluence (Fixed)",
            "registrationKey": reg_key,
            "subscriptionTier": "Enterprise",
            "enabledFeatures": ["all"]
        }
        await db.tenants.insert_one(new_tenant)
        print(f"Created Tenant: {tenant_id} with key {reg_key}")
    else:
        reg_key = tenant.get("registrationKey")
    
    print(f"Registration Key: {reg_key}")
    print(f"Registration Key: {reg_key}")
    
    # 2. Register Agent
    print("Registering Agent...")
    payload = {
        "registrationKey": reg_key,
        "hostname": "EILT0197",
        "platform": "Windows",
        "version": "2.0.0",
        "ipAddress": "172.29.192.1"
    }
    
    try:
        res = requests.post(f"{API_URL}/agents/register", json=payload)
        print(f"Register Status: {res.status_code}")
        print(f"Response: {res.text}")
    except Exception as e:
        print(f"Register Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
