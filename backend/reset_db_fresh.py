import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone
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

    # 8. Create Role Objects
    await db.roles.insert_one({
        "name": "Tenant Admin",
        "permissions": enterprise_permissions
    })
    await db.roles.insert_one({
        "name": "Super Admin",
        "permissions": enterprise_permissions + ["manage:tenants"]
    })

    # 9. Seed sample patches (Critical + High CVEs so patch management works immediately)
    print("Seeding sample patches for Exafluence...")
    sample_patches = [
        {
            "id": "patch-cve-2024-0001", "cve_id": "CVE-2024-0001",
            "name": "CVE-2024-0001", "title": "OpenSSL Critical RCE Vulnerability",
            "description": "Remote code execution via malformed TLS handshake.",
            "severity": "Critical", "cvss_score": 9.8,
            "affected_products": ["openssl 3.0.x", "openssl 1.1.x"],
            "status": "Available", "source": "seed",
            "tenantId": exafluence_id,
            "epss_score": 0.72, "exploit_probability": "72.00%",
            "synced_at": heartbeat,
        },
        {
            "id": "patch-cve-2024-0002", "cve_id": "CVE-2024-0002",
            "name": "CVE-2024-0002", "title": "Linux Kernel Privilege Escalation",
            "description": "Local privilege escalation via kernel use-after-free.",
            "severity": "High", "cvss_score": 7.8,
            "affected_products": ["linux kernel 5.x", "linux kernel 6.x"],
            "status": "Available", "source": "seed",
            "tenantId": exafluence_id,
            "epss_score": 0.45, "exploit_probability": "45.00%",
            "synced_at": heartbeat,
        },
        {
            "id": "patch-kb5034441", "cve_id": "CVE-2024-0003",
            "name": "KB5034441", "title": "Windows Defender Security Update",
            "description": "Patches CVE-2024-0003 in Windows Defender Engine.",
            "severity": "High", "cvss_score": 7.5,
            "kb_number": "KB5034441",
            "affected_products": ["windows 10", "windows 11", "windows server 2022"],
            "status": "Available", "source": "seed",
            "tenantId": exafluence_id,
            "epss_score": 0.31, "exploit_probability": "31.00%",
            "synced_at": heartbeat,
        },
    ]
    for p in sample_patches:
        await db.patches.update_one({"cve_id": p["cve_id"]}, {"$set": p}, upsert=True)

    # 10. Seed notification channel config (email defaults)
    print("Seeding notification config defaults...")
    await db.notification_config.update_one(
        {"type": "email"},
        {"$set": {
            "type": "email", "enabled": False,
            "smtp_host": "", "smtp_port": 587,
            "smtp_user": "", "smtp_password": "",
            "updated_at": heartbeat,
        }},
        upsert=True,
    )

    # 11. Seed default integration configs
    print("Seeding integration config defaults...")
    for integration in [
        {"type": "siem", "platform": "splunk", "enabled": False, "endpoint": "", "token": ""},
        {"type": "ticketing", "platform": "jira", "enabled": False, "instance_url": "", "auth_token": ""},
        {"type": "cmdb", "platform": "servicenow", "enabled": False, "instance_url": "", "auth_token": ""},
    ]:
        integration["updated_at"] = heartbeat
        await db.integration_configs.update_one(
            {"type": integration["type"], "platform": integration["platform"]},
            {"$set": integration},
            upsert=True,
        )

    # 12. Seed SIEM integration config stubs (disabled by default, admins enable via UI)
    print("Seeding SIEM config stubs...")
    for siem_cfg in [
        {
            "provider": "aws_cloudtrail", "enabled": False,
            "tenant_id": exafluence_id,
            "s3_bucket": "", "aws_access_key": "", "aws_secret_key": "",
            "region": "us-east-1", "description": "AWS CloudTrail S3 log ingestion",
        },
        {
            "provider": "okta", "enabled": False,
            "tenant_id": exafluence_id,
            "domain": "", "api_token": "",
            "description": "Okta system log ingestion",
        },
    ]:
        siem_cfg["updated_at"] = heartbeat
        await db.siem_configs.update_one(
            {"provider": siem_cfg["provider"], "tenant_id": siem_cfg["tenant_id"]},
            {"$set": siem_cfg},
            upsert=True,
        )

    print("\nReset and initialization complete!")
    print(f"Tenant: Exafluence ({exafluence_id})")
    print(f"Agent: 1 Online")
    print("Login: admin@exafluence.com (use configured password)")

    client.close()

if __name__ == "__main__":
    asyncio.run(reset())
