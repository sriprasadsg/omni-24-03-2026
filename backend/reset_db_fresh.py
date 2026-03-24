import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone, timedelta
import uuid
import bcrypt

# Configuration
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGODB_DB_NAME", "omni_platform")

def get_password_hash(password):
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

async def reset():
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DB_NAME]
    print(f"Connected to {DB_NAME}")

    # 1. Clear all collections
    collections = await db.list_collection_names()
    for coll in collections:
        if coll != "system.indexes":
            print(f"Clearing collection: {coll}")
            await db[coll].delete_many({})

    # 2. Exafluence Configuration
    exafluence_id = "tenant_exafluence"
    enterprise_features = [
        "view:dashboard", "view:cxo_dashboard", "view:profile", "view:insights", 
        "view:tracing", "view:logs", "view:network", "view:agents", "view:assets", 
        "view:patching", "view:security", "view:cloud_security", "view:threat_hunting", 
        "view:dspm", "view:attack_path", "view:sbom", "view:persistence", 
        "view:vulnerabilities", "view:devsecops", "view:dora_metrics", "view:service_catalog", 
        "view:chaos", "view:compliance", "view:ai_governance", "view:security_audit", 
        "view:audit_log", "view:reporting", "view:automation", "view:finops", 
        "view:developer_hub", "view:advanced_bi", "view:llmops", "view:unified_ops", 
        "view:swarm", "manage:settings"
    ]
    
    enterprise_permissions = [
        'view:dashboard', 'view:reporting', 'export:reports', 
        'view:agents', 'view:software_deployment', 'view:agent_logs', 'remediate:agents',
        'view:assets', 'view:patching', 'manage:patches', 'view:security', 
        'manage:security_cases', 'investigate:security', 'view:compliance',
        'manage:compliance_evidence', 'view:ai_governance', 'manage:ai_risks',
        'view:cloud_security', 'view:finops', 'view:audit_log',
        'manage:rbac', 'manage:api_keys', 'view:logs', 'view:profile',
        'view:automation', 'manage:automation', 'view:devsecops', 'manage:devsecops',
        'view:sbom', 'manage:sbom', 'view:insights', 'view:software_updates',
        'view:threat_hunting', 'view:tracing', 'view:dspm', 'view:attack_path',
        'view:service_catalog', 'view:dora_metrics', 'view:chaos', 'view:network',
        'view:zero_trust', 'view:developer_hub', 'manage:security_playbooks',
        'view:cxo_dashboard', 'view:unified_ops', 'view:advanced_bi',
        'view:sustainability', 'view:web_monitoring', 'view:analytics', 
        'view:threat_intel', 'view:vulnerabilities', 'view:persistence',
        'view:security_audit', 'view:mlops', 'view:llmops', 'view:automl',
        'manage:experiments', 'view:xai', 'view:governance', 'manage:playbooks',
        'view:swarm'
    ]

    # 3. Create Exafluence Tenant
    print(f"Creating Exafluence tenant ({exafluence_id})...")
    await db.tenants.insert_one({
        "id": exafluence_id,
        "name": "Exafluence",
        "subscriptionTier": "Enterprise",
        "enabledFeatures": enterprise_features,
        "createdAt": datetime.now(timezone.utc).isoformat()
    })

    # 4. Create Super Admin User
    print("Creating Super Admin user (super@omni.ai)...")
    await db.users.insert_one({
        "id": "user-admin",
        "email": "super@omni.ai",
        "name": "Super Admin",
        "password": get_password_hash("password123"),
        "role": "Super Admin",
        "tenantId": "platform-admin",
        "status": "Active",
        "permissions": enterprise_permissions + ["manage:tenants"],
        "createdAt": datetime.now(timezone.utc).isoformat()
    })

    # 5. Create Exafluence Admin User
    print("Creating Exafluence Admin user (admin@exafluence.com)...")
    await db.users.insert_one({
        "id": "user-exa-admin",
        "email": "admin@exafluence.com",
        "name": "Exafluence Admin",
        "password": get_password_hash("password123"),
        "role": "Tenant Admin",
        "tenantId": exafluence_id,
        "status": "Active",
        "permissions": enterprise_permissions,
        "createdAt": datetime.now(timezone.utc).isoformat()
    })

    # 6. Seed 1 Agent for Exafluence
    print("Seeding 1 Online agent for Exafluence...")
    # Use a very recent timestamp to avoid any monitor issues
    heartbeat = datetime.now(timezone.utc).isoformat()
    await db.agents.insert_one({
        "id": "agent-exa-1",
        "name": "EXA-PROD-01",
        "tenantId": exafluence_id,
        "status": "Online",
        "lastSeen": heartbeat,
        "ipAddress": "10.0.0.5",
        "os": "Linux",
        "version": "2.4.0"
    })

    # 7. Seed dummy asset and vulnerability for Exafluence
    print("Seeding dummy asset and vulnerability for Exafluence...")
    asset_id = "asset-exa-1"
    await db.assets.insert_one({
        "id": asset_id,
        "tenantId": exafluence_id,
        "name": "Main-DB-Server",
        "type": "Database",
        "status": "Active",
        "lastSeen": heartbeat
    })

    await db.vulnerabilities.insert_one({
        "id": "vuln-exa-1",
        "tenantId": exafluence_id,
        "assetId": asset_id,
        "cveId": "CVE-2024-9999",
        "severity": "High",
        "status": "Open",
        "affectedSoftware": "PostgreSQL",
        "description": "Critical SQL injection vulnerability.",
        "discoveredAt": heartbeat
    })

    # 8. Create Role Objects (Optional but good for robustness)
    await db.roles.insert_one({
        "name": "Tenant Admin",
        "permissions": enterprise_permissions
    })
    await db.roles.insert_one({
        "name": "Super Admin",
        "permissions": enterprise_permissions + ["manage:tenants"]
    })

    print("\nReset and initialization complete!")
    print(f"Tenant: Exafluence ({exafluence_id})")
    print(f"Agent: 1 Online")
    print(f"Login: admin@exafluence.com / password123")

    client.close()

if __name__ == "__main__":
    asyncio.run(reset())
