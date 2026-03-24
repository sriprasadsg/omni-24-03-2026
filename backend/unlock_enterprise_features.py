import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGODB_DB_NAME", "omni_platform")

# Full list of permission-based features as of 2026/2030 version
ENTERPRISE_FEATURES = [
    "view:dashboard", "view:cxo_dashboard", "view:profile", "view:insights", 
    "view:tracing", "view:logs", "view:network", "view:agents", "view:assets", 
    "view:patching", "view:security", "view:cloud_security", "view:threat_hunting", 
    "view:dspm", "view:attack_path", "view:sbom", "view:persistence", 
    "view:vulnerabilities", "view:devsecops", "view:dora_metrics", "view:service_catalog", 
    "view:chaos", "view:compliance", "view:ai_governance", "view:security_audit", 
    "view:audit_log", "view:reporting", "view:automation", "view:finops", 
    "view:developer_hub", "view:advanced_bi", "view:llmops", "view:unified_ops", 
    "view:swarm", "manage:settings", "manage:tenants"
]

async def unlock_all():
    print(f"Connecting to MongoDB at {MONGODB_URL}...")
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DB_NAME]
    
    tenants_collection = db.tenants
    
    print("Fetching all tenants...")
    tenants = await tenants_collection.find({}).to_list(length=1000)
    
    if not tenants:
        print("No tenants found in the database.")
        return

    print(f"Updating {len(tenants)} tenants to Enterprise tier with all features...")
    
    for tenant in tenants:
        tenant_id = tenant.get("id")
        tenant_name = tenant.get("name", "Unknown")
        
        print(f" - Unlocking: {tenant_name} ({tenant_id})")
        
        result = await tenants_collection.update_one(
            {"id": tenant_id},
            {
                "$set": {
                    "subscriptionTier": "Enterprise",
                    "enabledFeatures": ENTERPRISE_FEATURES,
                    "updatedAt": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        
        if result.modified_count > 0:
            print(f"   ✓ Successfully updated.")
        else:
            print(f"   ℹ Already up to date or no changes needed.")

    print("\n✅ All tenants have been unlocked successfully!")
    client.close()

if __name__ == "__main__":
    asyncio.run(unlock_all())
