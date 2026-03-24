from fastapi import APIRouter, Depends
from typing import List, Dict, Any
from database import get_database
from authentication_service import get_current_user
from auth_types import TokenData

print("Loading integration_endpoints...")
router = APIRouter(prefix="/api/integrations", tags=["Integrations"])

# Static list of supported integrations (Catalog)
SUPPORTED_INTEGRATIONS = [
    { "id": "pagerduty", "name": "PagerDuty", "description": "Trigger incidents for on-call teams.", "category": "Observability", "isEnabled": False, "config": { "apiKey": "" } },
    { "id": "jira", "name": "Jira", "description": "Create tickets for security cases and tasks.", "category": "Ticketing", "isEnabled": False, "config": { "apiUrl": "https://omni.atlassian.net", "apiToken": "", "projectKey": "SEC" } },
    { "id": "splunk", "name": "Splunk", "description": "Forward events and logs to your Splunk instance.", "category": "SIEM", "isEnabled": False, "config": {} },
    { "id": "datadog", "name": "Datadog", "description": "Correlate Omni-Agent data with Datadog metrics.", "category": "Observability", "isEnabled": False, "config": {} },
    { "id": "crowdstrike", "name": "CrowdStrike", "description": "Enrich findings with Falcon platform data.", "category": "Security", "isEnabled": False, "config": {} },
    { "id": "slack", "name": "Slack", "description": "Send notifications to Slack channels.", "category": "Communication", "isEnabled": False, "config": { "webhookUrl": "" } },
    { "id": "msteams", "name": "Microsoft Teams", "description": "Send notifications to Teams channels.", "category": "Communication", "isEnabled": False, "config": { "webhookUrl": "" } },
    { "id": "servicenow", "name": "ServiceNow", "description": "Sync assets and create incidents.", "category": "ITSM", "isEnabled": False, "config": { "instanceUrl": "", "username": "", "password": "" } },
    { "id": "aws-security-hub", "name": "AWS Security Hub", "description": "Import findings from AWS Security Hub.", "category": "Cloud Security", "isEnabled": False, "config": { "region": "", "accessKey": "", "secretKey": "" } },
    { "id": "github", "name": "GitHub", "description": "Scan repositories for vulnerabilities.", "category": "Developer Tools", "isEnabled": False, "config": { "accessToken": "" } }
]

@router.get("/configs")
async def list_integration_configs(current_user: TokenData = Depends(get_current_user)):
    """List all integration configurations"""
    db = get_database()
    # Fetch configurations for the tenant
    configs = await db.integrations.find({"tenantId": current_user.tenant_id}, {"_id": 0}).to_list(length=100)
    return configs

@router.post("/config")
async def save_integration_config(
    config: dict,
    current_user: TokenData = Depends(get_current_user)
):
    """Save integration configuration"""
    db = get_database()
    config["tenantId"] = current_user.tenant_id
    
    # Check if config exists, update it
    existing = await db.integrations.find_one({"tenantId": current_user.tenant_id, "id": config.get("id")})
    
    if existing:
        await db.integrations.update_one(
            {"tenantId": current_user.tenant_id, "id": config.get("id")},
            {"$set": config}
        )
    else:
        await db.integrations.insert_one(config)
        
    return {"success": True, "message": "Configuration saved", "id": config.get("id")}

@router.get("/list")
async def list_integrations(current_user: TokenData = Depends(get_current_user)):
    """List all integrations (catalog + status)"""
    db = get_database()
    
    # Fetch configured integrations from DB
    db_configs = await db.integrations.find({"tenantId": current_user.tenant_id}, {"_id": 0}).to_list(length=100)
    
    # Convert DB configs to a map for easy lookup
    config_map = {conf.get("id"): conf for conf in db_configs}
    
    results = []
    
    # Merge supported integrations with DB configs
    supported_ids = set(i["id"] for i in SUPPORTED_INTEGRATIONS)
    
    for integration in SUPPORTED_INTEGRATIONS:
        # Create a copy to avoid modifying the global list
        merged_integration = integration.copy()
        
        # Check if there is a config in DB
        if merged_integration["id"] in config_map:
            db_config = config_map[merged_integration["id"]]
            # Update fields from DB
            merged_integration["isEnabled"] = db_config.get("isEnabled", False)
            if "config" in db_config:
                 merged_integration["config"] = db_config["config"]
    
        results.append(merged_integration)
        
    # Add custom integrations (those in DB but not in SUPPORTED_INTEGRATIONS)
    for db_config in db_configs:
        if db_config.get("id") not in supported_ids:
            # This is a custom integration
            results.append(db_config)
        
    return results

@router.delete("/config/{integration_id}")
async def delete_integration_config(
    integration_id: str,
    current_user: TokenData = Depends(get_current_user)
):
    """Delete an integration configuration"""
    db = get_database()
    result = await db.integrations.delete_one(
        {"tenantId": current_user.tenant_id, "id": integration_id}
    )
    if result.deleted_count == 0:
        # Not in DB (could be a built-in default) — just return success
        return {"success": True, "message": f"Integration '{integration_id}' removed (no persistent config found)"}
    return {"success": True, "message": f"Integration '{integration_id}' deleted successfully"}

@router.post("/test")
async def test_integration(
    request: dict,
    current_user: TokenData = Depends(get_current_user)
):
    """Test integration (Mock)"""
    print(f"Testing integration: {request}")
    # Simulate success for verification
    return {"success": True, "message": f"Test notification sent to {request.get('platform', 'unknown')}"}
