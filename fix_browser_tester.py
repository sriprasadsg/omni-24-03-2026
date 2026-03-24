
import asyncio
from database import connect_to_mongo, get_database, close_mongo_connection

async def fix_browser_tester():
    await connect_to_mongo()
    db = get_database()
    
    # 1. Find Browser Tester
    user = await db.users.find_one({"name": "Browser Tester"})
    if not user:
        print("Browser Tester user not found.")
        await close_mongo_connection()
        return
    
    tenant_id = user.get("tenantId")
    print(f"Fixing tenant {tenant_id} for Browser Tester...")
    
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
    
    # 2. Update Tenant
    await db.tenants.update_one(
        {"id": tenant_id},
        {"$set": {
            "subscriptionTier": "Enterprise",
            "enabledFeatures": enterprise_features
        }}
    )
    
    # 3. Update User Permissions
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
        'security_audit', 'view:mlops', 'view:llmops', 'view:automl',
        'manage:experiments', 'view:xai', 'view:governance', 'manage:playbooks',
        'view:swarm'
    ]
    
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {
            "subscriptionTier": "Enterprise",
            "permissions": enterprise_permissions
        }}
    )
    
    print("SUCCESS: Browser Tester and their tenant updated to Enterprise.")
    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(fix_browser_tester())
