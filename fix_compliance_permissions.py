import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGODB_DB_NAME", "omni_platform")

REQUIRED_PERMISSIONS = [
    "view:compliance", 
    "manage:compliance_evidence", 
    "view:ai_governance", 
    "manage:ai_risks",
    "view:security_audit"
]

async def fix_permissions():
    print(f"Connecting to MongoDB at {MONGODB_URL}...")
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DB_NAME]
    
    # 1. Fix Role Permissions
    print("Updating 'Tenant Admin' role permissions...")
    role = await db.roles.find_one({"name": "Tenant Admin"})
    if role:
        existing_perms = role.get("permissions", [])
        new_perms = list(set(existing_perms + REQUIRED_PERMISSIONS))
        await db.roles.update_one(
            {"name": "Tenant Admin"},
            {"$set": {"permissions": new_perms}}
        )
        print(f"   ✓ Updated 'Tenant Admin' role with {len(REQUIRED_PERMISSIONS)} perms.")
    else:
        print("   ⚠ 'Tenant Admin' role not found.")

    # 2. Fix Tenant Features
    print("Updating all tenants with compliance features...")
    tenants = await db.tenants.find({}).to_list(length=1000)
    for tenant in tenants:
        tenant_id = tenant.get("id")
        existing_features = tenant.get("enabledFeatures", [])
        new_features = list(set(existing_features + REQUIRED_PERMISSIONS))
        
        await db.tenants.update_one(
            {"id": tenant_id},
            {"$set": {
                "enabledFeatures": new_features,
                "subscriptionTier": "Enterprise"
            }}
        )
        print(f"   ✓ Updated tenant {tenant_id}")

    print("\n✅ Permissions and features fixed!")
    client.close()

if __name__ == "__main__":
    asyncio.run(fix_permissions())
