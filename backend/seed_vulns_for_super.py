import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone
import uuid
import bcrypt

# Configuration
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGODB_DB_NAME", "omni_platform")

def get_password_hash(password):
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

async def seed_data():
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DB_NAME]
    print(f"Connected to {DB_NAME}")

    email = "super@omni.ai"

    # 1. Get User and their Tenant
    user = await db.users.find_one({"email": email})
    if not user:
        print(f"Creating user {email}...")
        # Create user if not exists (fallback)
        tenant_id = "tenant-super-admin"
        tenant = await db.tenants.find_one({"id": tenant_id})
        if not tenant:
             await db.tenants.insert_one({
                "id": tenant_id,
                "name": "Super Admin Tenant",
                "subscriptionTier": "Enterprise",
                "enabledFeatures": ["agents", "assets"],
                "createdAt": datetime.now(timezone.utc).isoformat()
             })
        
        user = {
            "id": f"user-{uuid.uuid4().hex[:8]}",
            "email": email,
            "name": "Super Admin",
            "password": get_password_hash("password123"),
            "role": "Super Admin",
            "tenantId": tenant_id,
            "status": "Active",
            "createdAt": datetime.now(timezone.utc).isoformat()
        }
        await db.users.insert_one(user)
    else:
        tenant_id = user.get("tenantId")
        print(f"User {email} exists. Using Tenant ID: {tenant_id}")

    print(f"Seeding data for Tenant: {tenant_id} (User: {email})")

    # 3. Ensure Asset Exists
    asset = await db.assets.find_one({"tenantId": tenant_id})
    if not asset:
        print("Creating a dummy asset...")
        asset_id = f"asset-{uuid.uuid4().hex[:8]}"
        asset = {
            "id": asset_id,
            "tenantId": tenant_id,
            "name": "Production-Server-01",
            "type": "Server",
            "status": "Active",
            "lastSeen": datetime.now(timezone.utc).isoformat()
        }
        await db.assets.insert_one(asset)
    else:
        asset_id = asset["id"]
    
    print(f"Using Asset: {asset_id}")

    # 4. Insert Vulnerabilities
    vulns = [
        {
            "cveId": "CVE-2024-1234",
            "severity": "Critical",
            "status": "Open",
            "affectedSoftware": "Apache Log4j",
            "description": "Remote Code Execution vulnerability in Log4j.",
            "discoveredAt": datetime.now(timezone.utc).isoformat()
        },
        {
            "cveId": "CVE-2023-5678",
            "severity": "High",
            "status": "Open",
            "affectedSoftware": "OpenSSL",
            "description": "Buffer overflow in OpenSSL encryption.",
            "discoveredAt": datetime.now(timezone.utc).isoformat()
        },
         {
            "cveId": "CVE-2023-9012",
            "severity": "Medium",
            "status": "Patched",
            "affectedSoftware": "Nginx",
            "description": "Configuration issue allowing information disclosure.",
            "discoveredAt": datetime.now(timezone.utc).isoformat()
        }
    ]

    count = 0
    for v in vulns:
        # Check if exists
        exists = await db.vulnerabilities.find_one({
            "tenantId": tenant_id,
            "cveId": v["cveId"],
            "assetId": asset_id
        })
        
        if not exists:
            doc = v.copy()
            doc["tenantId"] = tenant_id
            doc["assetId"] = asset_id
            doc["id"] = f"vuln-{uuid.uuid4().hex[:8]}"
            await db.vulnerabilities.insert_one(doc)
            count += 1
            print(f"Inserted {v['cveId']}")
        else:
            print(f"Skipped {v['cveId']} (already exists)")

    print(f"Seeding complete. Added {count} vulnerabilities.")
    client.close()

if __name__ == "__main__":
    asyncio.run(seed_data())
