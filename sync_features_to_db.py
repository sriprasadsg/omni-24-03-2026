
import asyncio
import os
from datetime import datetime
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

# Load environment variables
load_dotenv()

MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGODB_DB_NAME", "omni_platform")

# Definitive List of Features (Source of Truth from Sidebar.tsx)
FEATURES = [
    # Main
    {"category": "Main", "name": "Dashboard", "key": "view:dashboard", "id": "dashboard"},
    {"category": "Main", "name": "CXO Insights", "key": "view:cxo_dashboard", "id": "cxo"},
    {"category": "Main", "name": "My Tasks", "key": "view:profile", "id": "tasks"},

    # Observability
    {"category": "Observability", "name": "Proactive Insights", "key": "view:insights", "id": "proactiveInsights"},
    {"category": "Observability", "name": "Distributed Tracing", "key": "view:tracing", "id": "distributedTracing"},
    {"category": "Observability", "name": "Log Explorer", "key": "view:logs", "id": "logExplorer"},
    {"category": "Observability", "name": "Network Observability", "key": "view:network", "id": "networkObservability"},

    # Infrastructure
    {"category": "Infrastructure", "name": "Agents", "key": "view:agents", "id": "agents"},
    {"category": "Infrastructure", "name": "Assets", "key": "view:assets", "id": "assetManagement"},
    {"category": "Infrastructure", "name": "Patch Management", "key": "view:patching", "id": "patchManagement"},

    # Security
    {"category": "Security", "name": "Security Dashboard", "key": "view:security", "id": "security"},
    {"category": "Security", "name": "Cloud Security (CSPM)", "key": "view:cloud_security", "id": "cloudSecurity"},
    {"category": "Security", "name": "Threat Hunting", "key": "view:threat_hunting", "id": "threatHunting"},
    {"category": "Security", "name": "Data Security (DSPM)", "key": "view:dspm", "id": "dataSecurity"},
    {"category": "Security", "name": "Attack Path Analysis", "key": "view:attack_path", "id": "attackPath"},
    {"category": "Security", "name": "SBOM Management", "key": "view:sbom", "id": "sbom"},
    {"category": "Security", "name": "Persistence Hunting", "key": "view:persistence", "id": "persistence"},
    {"category": "Security", "name": "Vulnerabilities", "key": "view:vulnerabilities", "id": "vulnerabilityManagement"},

    # DevOps
    {"category": "DevOps", "name": "DevSecOps", "key": "view:devsecops", "id": "devsecops"},
    {"category": "DevOps", "name": "DORA Metrics", "key": "view:dora_metrics", "id": "doraMetrics"},
    {"category": "DevOps", "name": "Service Catalog (IDP)", "key": "view:service_catalog", "id": "serviceCatalog"},
    {"category": "DevOps", "name": "Chaos Engineering", "key": "view:chaos", "id": "chaosEngineering"},
    {"category": "DevOps", "name": "Jobs & Workflows", "key": "view:jobs", "id": "jobs"},

    # Governance
    {"category": "Governance & Compliance", "name": "Compliance", "key": "view:compliance", "id": "compliance"},
    {"category": "Governance & Compliance", "name": "AI Governance", "key": "view:ai_governance", "id": "aiGovernance"},
    {"category": "Governance & Compliance", "name": "Security Audit", "key": "view:security_audit", "id": "securityAudit"},
    {"category": "Governance & Compliance", "name": "Audit Log", "key": "view:audit_log", "id": "auditLog"},

    # Operations
    {"category": "Operations", "name": "Reporting", "key": "view:reporting", "id": "reporting"},
    {"category": "Operations", "name": "Automation", "key": "view:automation", "id": "automation"},
    {"category": "Operations", "name": "FinOps & Billing", "key": "view:finops", "id": "finops"},
    {"category": "Operations", "name": "Developer Hub", "key": "view:developer_hub", "id": "developer_hub"},

    # Advanced
    {"category": "Advanced", "name": "Advanced BI", "key": "view:advanced_bi", "id": "advancedBi"},
    {"category": "Advanced", "name": "LLMOps", "key": "view:llmops", "id": "llmops"},
    {"category": "Advanced", "name": "Unified Ops", "key": "view:unified_ops", "id": "unifiedOps"},
    {"category": "Advanced", "name": "Swarm Intelligence", "key": "view:swarm", "id": "swarm"},

    # Administration
    {"category": "Administration", "name": "Settings", "key": "manage:settings", "id": "settings"},
    {"category": "Administration", "name": "Tenant Management", "key": "manage:tenants", "id": "tenantManagement"},
    {"category": "Administration", "name": "Service Pricing", "key": "manage:tenants", "id": "servicePricing"},
    {"category": "Administration", "name": "System Health", "key": "manage:settings", "id": "systemHealth"},
]

async def sync_features():
    print(f"Connecting to MongoDB at {MONGODB_URL}...")
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DB_NAME]
    collection = db.system_features

    # Drop incorrect index if it exists
    try:
        await collection.drop_index("key_1")
        print("Dropped incorrect unique index on 'key'")
    except Exception:
        pass

    # Create indexes if they don't exist (handled by backend usually, but ensuring here)
    await collection.create_index("id", unique=True)
    await collection.create_index("category")

    total_synced = 0
    timestamp = datetime.now().isoformat()

    print(f"Syncing {len(FEATURES)} features to database...")

    for feature in FEATURES:
        # doc = SystemFeature(...)
        doc = {
            "id": feature["id"],
            "name": feature["name"],
            "category": feature["category"],
            "key": feature["key"],
            "verificationStatus": "Active",
            "lastVerifiedAt": timestamp,
            "metadata": {
                "source": "sync_script",
                "syncedBy": "Super Admin"
            }
        }
        
        # Upsert: Update if exists, insert if not
        result = await collection.update_one(
            {"key": feature["key"], "id": feature["id"]}, # Match on key AND id to be specific
            {"$set": doc},
            upsert=True
        )
        total_synced += 1
    
    # Delete deprecated features (present in DB but not in this list)
    # Get all keys in DB
    all_db_features = await collection.find({}).to_list(None)
    current_keys = set(f["key"] + ":" + f["id"] for f in FEATURES)
    
    deprecated_count = 0
    for db_feat in all_db_features:
        db_unique_key = db_feat.get("key") + ":" + db_feat.get("id")
        if db_unique_key not in current_keys:
            print(f"Purging legacy feature from DB: {db_feat.get('name')} ({db_unique_key})")
            await collection.delete_one({"_id": db_feat["_id"]})
            deprecated_count += 1

    print(f"✅ Sync Complete.")
    print(f"   Total Active Features: {total_synced}")
    print(f"   deprecated/Missing: {deprecated_count}")

    client.close()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(sync_features())
