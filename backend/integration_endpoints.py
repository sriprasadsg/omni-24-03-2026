from datetime import timezone
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Dict, Any
from database import get_database
from integration_service import get_integration_service
from authentication_service import get_current_user

router = APIRouter(prefix="/api/integrations", tags=["Integrations"])

_SUPER_ADMIN_ROLES = {"Super Admin", "superadmin", "super_admin", "platform-admin"}

def _resolve_tenant(current_user, requested_tenant_id: Optional[str] = None) -> str:
    """Return the tenant ID the caller is authorised to act on."""
    role = getattr(current_user, "role", "") or ""
    if role in _SUPER_ADMIN_ROLES and requested_tenant_id:
        return requested_tenant_id
    tid = getattr(current_user, "tenant_id", None) or None
    if not tid:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Tenant context required")
    return tid


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
    tenant_id: Optional[str] = None,
    current_user=Depends(get_current_user),
    db=Depends(get_database)
):
    """Get all integration configs for tenant"""
    resolved = _resolve_tenant(current_user, tenant_id)
    service = get_integration_service(db)
    return await service.get_all_configs(resolved)

@router.post("/config")
async def save_integration_config(
    config: IntegrationConfig,
    tenant_id: Optional[str] = None,
    current_user=Depends(get_current_user),
    db=Depends(get_database)
):
    """Save integration config"""
    resolved = _resolve_tenant(current_user, tenant_id)
    service = get_integration_service(db)
    result = await service.save_config(resolved, config.dict())
    return result

@router.post("/test")
async def test_integration(
    request: TestIntegrationRequest,
    current_user=Depends(get_current_user),
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
    "slack":         ("soar_connectors_messaging", "SlackConnector"),
    "teams":         ("soar_connectors_messaging", "TeamsConnector"),
    "pagerduty":     ("soar_connectors_messaging", "PagerDutyConnector"),
    "email_gateway": ("soar_connectors_messaging", "EmailGatewayConnector"),
    "firewall":      ("soar_connectors_security", "FirewallConnector"),
    "edr":           ("soar_connectors_security", "EDRConnector"),
    "cloud":         ("soar_connectors_cloud", "CloudProviderConnector"),
    "jira":          ("soar_integrations", "JiraConnector"),
    "servicenow":    ("soar_integrations", "ServiceNowConnector"),
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
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Test connectivity for a named SOAR connector (slack, jira, edr, firewall, etc.)"""
    saved = await db.soar_connector_configs.find_one(
        {"connector": connector_name.lower()}, {"_id": 0}
    ) or {}
    _SENSITIVE_CONFIG_FIELDS = {"api_key", "token", "api_token", "secret_key", "password", "credentials_json", "auth_token", "secret"}
    merged = {**saved.get("config", {})}
    if config:
        for k, v in config.items():
            if k not in _SENSITIVE_CONFIG_FIELDS:
                merged[k] = v

    try:
        connector = _build_connector(connector_name, merged)
        ok = await connector.test_connection()
        return {"success": ok, "connector": connector_name, "message": "Connected" if ok else "Connection failed"}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/connectors/{connector_name}/execute")
async def execute_connector_action(
    connector_name: str,
    body: ConnectorExecuteRequest,
    current_user=Depends(get_current_user),
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
        await db.soar_execution_log.insert_one({
            "connector": connector_name,
            "action": body.action,
            "params": body.params,
            "result": result,
            "executed_by": getattr(current_user, "username", None),
            "tenant_id": getattr(current_user, "tenant_id", None),
            "executed_at": __import__("datetime").datetime.now(timezone.utc).isoformat(),
        })
        return result
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=400, detail="Bad request")
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/connectors/{connector_name}/config")
async def save_connector_config(
    connector_name: str,
    config: Dict[str, Any],
    current_user=Depends(get_current_user),
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
async def get_connector_config(
    connector_name: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Get saved config for a connector (secrets are redacted)."""
    doc = await db.soar_connector_configs.find_one(
        {"connector": connector_name.lower()}, {"_id": 0}
    )
    if not doc:
        return {"connector": connector_name, "config": {}}
    cfg = dict(doc.get("config", {}))
    for sensitive in ("api_key", "token", "api_token", "secret_key", "password", "credentials_json"):
        if sensitive in cfg:
            cfg[sensitive] = "***"
    return {"connector": connector_name, "config": cfg}


@router.get("/connectors")
async def list_connectors(current_user=Depends(get_current_user)):
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
