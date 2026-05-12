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
    """Test integration by sending a real test event to the configured endpoint."""
    platform = request.get("platform", "unknown")
    db = get_database()

    # Load persisted config for this integration
    config_doc = await db.integrations.find_one(
        {"tenantId": current_user.tenant_id, "id": platform}, {"_id": 0}
    ) or {}
    config = config_doc.get("config", {})

    try:
        import httpx

        if platform == "slack":
            webhook_url = config.get("webhookUrl") or request.get("webhookUrl", "")
            if not webhook_url:
                return {"success": False, "message": "Slack webhookUrl not configured."}
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(webhook_url, json={"text": ":white_check_mark: Omni-Agent test notification"})
            if resp.status_code in (200, 204):
                return {"success": True, "message": "Slack test message sent successfully."}
            return {"success": False, "message": f"Slack returned HTTP {resp.status_code}."}

        if platform == "msteams":
            webhook_url = config.get("webhookUrl") or request.get("webhookUrl", "")
            if not webhook_url:
                return {"success": False, "message": "Teams webhookUrl not configured."}
            payload = {"@type": "MessageCard", "text": "Omni-Agent test notification"}
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(webhook_url, json=payload)
            if resp.status_code in (200, 204):
                return {"success": True, "message": "Teams test message sent successfully."}
            return {"success": False, "message": f"Teams returned HTTP {resp.status_code}."}

        if platform == "pagerduty":
            api_key = config.get("apiKey") or request.get("apiKey", "")
            if not api_key:
                return {"success": False, "message": "PagerDuty apiKey not configured."}
            headers = {"Authorization": f"Token token={api_key}", "Content-Type": "application/json"}
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get("https://api.pagerduty.com/abilities", headers=headers)
            if resp.status_code == 200:
                return {"success": True, "message": "PagerDuty API key validated successfully."}
            return {"success": False, "message": f"PagerDuty returned HTTP {resp.status_code}."}

        if platform == "jira":
            api_url = config.get("apiUrl") or request.get("apiUrl", "")
            api_token = config.get("apiToken") or request.get("apiToken", "")
            if not api_url or not api_token:
                return {"success": False, "message": "Jira apiUrl or apiToken not configured."}
            import base64
            auth = base64.b64encode(f"user:{api_token}".encode()).decode()
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{api_url}/rest/api/3/myself", headers={"Authorization": f"Basic {auth}"})
            if resp.status_code == 200:
                return {"success": True, "message": "Jira API connection verified."}
            return {"success": False, "message": f"Jira returned HTTP {resp.status_code}."}

        # Generic: no test logic implemented for this platform
        return {"success": True, "message": f"Integration '{platform}' saved — no live test available for this platform type."}

    except httpx.ConnectError:
        return {"success": False, "message": f"Could not connect to {platform} endpoint. Check the URL and network access."}
    except Exception as e:
        return {"success": False, "message": f"Test failed: {str(e)}"}
