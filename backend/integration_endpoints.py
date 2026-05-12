from datetime import timezone
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from database import get_database
from integration_service import get_integration_service

router = APIRouter(prefix="/api/integrations", tags=["Integrations"])

# --- Models ---
class IntegrationConfig(BaseModel):
    type: str # siem, chatops, ticketing
    platform: str # splunk, slack, jira
    enabled: bool
    endpoint: Optional[str] = None
    token: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    webhook_url: Optional[str] = None
    instance_url: Optional[str] = None
    api_key: Optional[str] = None
    project_key: Optional[str] = None
    
class TestIntegrationRequest(BaseModel):
    type: str
    platform: str
    config: Dict[str, Any]

# --- Endpoints ---

@router.get("/configs")
async def get_integration_configs(
    tenant_id: Optional[str] = "default",  # MVP default
    db=Depends(get_database)
):
    """Get all integration configs for tenant"""
    service = get_integration_service(db)
    return await service.get_all_configs(tenant_id)

@router.post("/config")
async def save_integration_config(
    config: IntegrationConfig,
    tenant_id: Optional[str] = "default",
    db=Depends(get_database)
):
    """Save integration config"""
    service = get_integration_service(db)
    result = await service.save_config(tenant_id, config.dict())
    return result

@router.post("/test")
async def test_integration(
    request: TestIntegrationRequest,
    db=Depends(get_database)
):
    """Test integration connection"""
    service = get_integration_service(db)

    if request.type == "siem":
        return await service.test_siem_connection(request.platform, request.config)
    elif request.type == "chatops":
        return await service.send_to_chatops(
            title="Integration Test",
            message=f"This is a test message from Omni-Agent Platform to {request.platform}.",
            severity="info",
            platform=request.platform
        )
    else:
        return {"success": False, "error": f"Testing not supported for {request.type}"}


# ── SOAR Connector Execution API ──────────────────────────────────────────────

_CONNECTOR_MAP = {
    "slack":         ("soar_integrations", "SlackConnector"),
    "teams":         ("soar_integrations", "TeamsConnector"),
    "jira":          ("soar_integrations", "JiraConnector"),
    "servicenow":    ("soar_integrations", "ServiceNowConnector"),
    "pagerduty":     ("soar_integrations", "PagerDutyConnector"),
    "firewall":      ("soar_integrations", "FirewallConnector"),
    "edr":           ("soar_integrations", "EDRConnector"),
    "email_gateway": ("soar_integrations", "EmailGatewayConnector"),
    "cloud":         ("soar_integrations", "CloudProviderConnector"),
}


def _build_connector(connector_name: str, config: dict):
    """Instantiate the right connector class from the registry."""
    entry = _CONNECTOR_MAP.get(connector_name.lower())
    if not entry:
        raise HTTPException(status_code=404, detail=f"Unknown connector: {connector_name}")
    module_name, class_name = entry
    import importlib
    mod = importlib.import_module(module_name)
    cls = getattr(mod, class_name)
    return cls(config)


class ConnectorExecuteRequest(BaseModel):
    action: str
    params: Dict[str, Any] = {}
    config: Optional[Dict[str, Any]] = None  # override saved config


@router.post("/connectors/{connector_name}/test")
async def test_connector(
    connector_name: str,
    config: Optional[Dict[str, Any]] = None,
    db=Depends(get_database),
):
    """Test connectivity for a named SOAR connector (slack, jira, edr, firewall, etc.)"""
    # Load saved config from DB and merge with any supplied override
    saved = await db.soar_connector_configs.find_one(
        {"connector": connector_name.lower()}, {"_id": 0}
    ) or {}
    merged = {**saved.get("config", {}), **(config or {})}

    try:
        connector = _build_connector(connector_name, merged)
        ok = await connector.test_connection()
        return {"success": ok, "connector": connector_name, "message": "Connected" if ok else "Connection failed"}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/connectors/{connector_name}/execute")
async def execute_connector_action(
    connector_name: str,
    body: ConnectorExecuteRequest,
    db=Depends(get_database),
):
    """Execute an action on a named SOAR connector."""
    saved = await db.soar_connector_configs.find_one(
        {"connector": connector_name.lower()}, {"_id": 0}
    ) or {}
    merged = {**saved.get("config", {}), **(body.config or {})}

    try:
        connector = _build_connector(connector_name, merged)
        result = await connector.execute(body.action, body.params)
        # Audit log the execution
        await db.soar_execution_log.insert_one({
            "connector": connector_name,
            "action": body.action,
            "params": body.params,
            "result": result,
            "executed_at": __import__("datetime").datetime.now(timezone.utc).isoformat(),
        })
        return result
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.put("/connectors/{connector_name}/config")
async def save_connector_config(
    connector_name: str,
    config: Dict[str, Any],
    db=Depends(get_database),
):
    """Persist a connector's configuration in the database."""
    await db.soar_connector_configs.update_one(
        {"connector": connector_name.lower()},
        {"$set": {"connector": connector_name.lower(), "config": config,
                  "updated_at": __import__("datetime").datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"success": True, "connector": connector_name}


@router.get("/connectors/{connector_name}/config")
async def get_connector_config(connector_name: str, db=Depends(get_database)):
    """Get saved config for a connector (secrets are redacted)."""
    doc = await db.soar_connector_configs.find_one(
        {"connector": connector_name.lower()}, {"_id": 0}
    )
    if not doc:
        return {"connector": connector_name, "config": {}}
    # Redact sensitive fields
    cfg = dict(doc.get("config", {}))
    for sensitive in ("api_key", "token", "api_token", "secret_key", "password", "credentials_json"):
        if sensitive in cfg:
            cfg[sensitive] = "***"
    return {"connector": connector_name, "config": cfg}


@router.get("/connectors")
async def list_connectors():
    """List all available SOAR connector names and their supported actions."""
    return {
        "connectors": [
            {"name": "slack",         "actions": ["send_message", "request_approval"]},
            {"name": "teams",         "actions": ["send_message", "send_adaptive_card"]},
            {"name": "jira",          "actions": ["create_ticket", "update_ticket", "add_comment"]},
            {"name": "pagerduty",     "actions": ["create_incident", "resolve_incident"]},
            {"name": "firewall",      "actions": ["block_ip", "unblock_ip", "create_rule"]},
            {"name": "edr",           "actions": ["isolate_endpoint", "release_endpoint", "quarantine_file", "scan_endpoint"]},
            {"name": "email_gateway", "actions": ["block_sender", "quarantine_email", "release_email"]},
            {"name": "cloud",         "actions": ["quarantine_instance", "snapshot_instance", "revoke_credentials"]},
        ]
    }

