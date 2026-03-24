"""
Ticketing Endpoints — /api/ticketing/*
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from authentication_service import get_current_user
import ticketing_service

router = APIRouter(prefix="/api/ticketing", tags=["Ticketing"])


class TicketingConfigRequest(BaseModel):
    provider: str  # "jira" | "servicenow"
    jira_url: str | None = None
    jira_project_key: str | None = None
    jira_email: str | None = None
    jira_api_token: str | None = None
    jira_issue_type: str = "Bug"
    snow_instance: str | None = None
    snow_username: str | None = None
    snow_password: str | None = None
    zoho_org_id: str | None = None
    zoho_department_id: str | None = None
    zoho_token: str | None = None
    custom_webhook_url: str | None = None
    custom_webhook_method: str = "POST"
    custom_webhook_headers: dict | None = {}
    custom_webhook_payload: dict | None = {}
    auto_create_severity: list[str] = ["critical"]


class ManualTicketRequest(BaseModel):
    alert_id: str
    provider: str | None = None  # Override tenant default


class TestConnectionRequest(BaseModel):
    provider: str


@router.get("/config")
async def get_config(current_user=Depends(get_current_user)):
    config = await ticketing_service.get_ticketing_config(current_user.tenant_id or "default")
    if not config:
        return {}
    # Mask credentials
    config.pop("_id", None)
    if config.get("jira_api_token"):
        config["jira_api_token"] = "***masked***"
    if config.get("snow_password"):
        config["snow_password"] = "***masked***"
    if config.get("zoho_token"):
        config["zoho_token"] = "***masked***"
    # Mask custom headers if sensitive keywords found
    if config.get("custom_webhook_headers"):
        headers = config["custom_webhook_headers"].copy()
        for k in headers:
            if any(s in k.lower() for s in ["key", "token", "auth", "pwd", "secret"]):
                headers[k] = "***masked***"
        config["custom_webhook_headers"] = headers
    return config


@router.post("/config")
async def save_config(req: TicketingConfigRequest, current_user=Depends(get_current_user)):
    if current_user.role not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Admin only")
    return await ticketing_service.save_ticketing_config(
        current_user.tenant_id or "default", req.dict()
    )


@router.post("/test")
async def test_connection(req: TestConnectionRequest, current_user=Depends(get_current_user)):
    config = await ticketing_service.get_ticketing_config(current_user.tenant_id or "default")
    if not config:
        return {"success": False, "error": "No ticketing config found"}

    dummy_alert = {
        "alert_id": "test-alert-001",
        "type": "connection_test",
        "severity": "low",
        "description": "This is a connectivity test from the Omni-Agent Platform.",
        "hostname": "test-host",
        "process": {"name": "test.exe", "pid": 0, "sha256": "0" * 64},
        "mitre_technique": "N/A",
    }

    if req.provider == "jira":
        return await ticketing_service.create_jira_ticket(dummy_alert, config)
    elif req.provider == "servicenow":
        return await ticketing_service.create_servicenow_incident(dummy_alert, config)
    elif req.provider == "zoho":
        return await ticketing_service.create_zoho_desk_ticket(dummy_alert, config)
    elif req.provider == "custom":
        return await ticketing_service.create_custom_webhook_ticket(dummy_alert, config)
    return {"success": False, "error": f"Unknown provider: {req.provider}"}


@router.post("/create")
async def create_ticket(req: ManualTicketRequest, current_user=Depends(get_current_user)):
    """Manually create a ticket from an alert ID."""
    from database import get_database
    db = get_database()
    alert = await db.edr_alerts.find_one({"alert_id": req.alert_id})
    if not alert:
        alert = await db.security_alerts.find_one({"alert_id": req.alert_id})
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert["_id"] = str(alert.get("_id", ""))
    config = await ticketing_service.get_ticketing_config(current_user.tenant_id or "default")
    if not config:
        raise HTTPException(status_code=400, detail="Ticketing not configured")

    provider = req.provider or config.get("provider", "jira")
    if provider == "jira":
        return await ticketing_service.create_jira_ticket(alert, config)
    elif provider == "servicenow":
        return await ticketing_service.create_servicenow_incident(alert, config)
    elif provider == "zoho":
        return await ticketing_service.create_zoho_desk_ticket(alert, config)
    elif provider == "custom":
        return await ticketing_service.create_custom_webhook_ticket(alert, config)
    raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")


@router.get("/tickets")
async def list_tickets(current_user=Depends(get_current_user)):
    return await ticketing_service.list_tickets(current_user.tenant_id or "default")
