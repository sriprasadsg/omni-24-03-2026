"""
Ticketing Service — Jira, ServiceNow, PagerDuty, OpsGenie, Slack, Teams
------------------------------------------------------------------------
Creates incidents/tickets from platform alerts.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional
from database import get_database

logger = logging.getLogger(__name__)

# Severity → priority mappings
JIRA_PRIORITY_MAP = {
    "critical": "Highest",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
    "info": "Lowest",
}

SNOW_URGENCY_MAP = {
    "critical": 1,
    "high": 2,
    "medium": 3,
    "low": 4,
}


# ─── Config Store ─────────────────────────────────────────────────────────────

async def get_ticketing_config(tenant_id: str) -> Optional[dict]:
    db = get_database()
    config = await db.ticketing_configs.find_one({"tenant_id": tenant_id})
    return config


async def save_ticketing_config(tenant_id: str, config: dict) -> dict:
    db = get_database()
    doc = {
        "tenant_id": tenant_id,
        "provider": config.get("provider"),           # "jira" | "servicenow"
        "jira_url": config.get("jira_url"),
        "jira_project_key": config.get("jira_project_key"),
        "jira_email": config.get("jira_email"),
        "jira_api_token": config.get("jira_api_token"),
        "jira_issue_type": config.get("jira_issue_type", "Bug"),
        "snow_instance": config.get("snow_instance"),
        "snow_username": config.get("snow_username"),
        "snow_password": config.get("snow_password"),
        "zoho_org_id": config.get("zoho_org_id"),
        "zoho_department_id": config.get("zoho_department_id"),
        "zoho_token": config.get("zoho_token"),
        "custom_webhook_url": config.get("custom_webhook_url"),
        "custom_webhook_method": config.get("custom_webhook_method", "POST"),
        "custom_webhook_headers": config.get("custom_webhook_headers", {}),
        "custom_webhook_payload": config.get("custom_webhook_payload", {}),
        "auto_create_severity": config.get("auto_create_severity", ["critical"]),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.ticketing_configs.update_one(
        {"tenant_id": tenant_id}, {"$set": doc}, upsert=True
    )
    return {"success": True}


# ─── Jira ────────────────────────────────────────────────────────────────────

async def create_jira_ticket(alert: dict, config: dict) -> dict:
    """Create a Jira issue from a platform alert."""
    try:
        import httpx, base64
        jira_url = config.get("jira_url", "").rstrip("/")
        auth = base64.b64encode(
            f"{config['jira_email']}:{config['jira_api_token']}".encode()
        ).decode()
        headers = {
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
        }
        severity = alert.get("severity", "medium").lower()
        payload = {
            "fields": {
                "project": {"key": config.get("jira_project_key", "SEC")},
                "summary": f"[{severity.upper()}] {alert.get('type', 'Security Alert').replace('_', ' ')} — {alert.get('hostname', 'Unknown Host')}",
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [{
                        "type": "paragraph",
                        "content": [{"type": "text", "text": (
                            f"Alert ID: {alert.get('alert_id', 'N/A')}\n"
                            f"Description: {alert.get('description', '')}\n"
                            f"Process: {alert.get('process', {}).get('name', 'N/A')} (PID {alert.get('process', {}).get('pid', 'N/A')})\n"
                            f"SHA256: {alert.get('process', {}).get('sha256', 'N/A')}\n"
                            f"MITRE Technique: {alert.get('mitre_technique', 'N/A')}\n"
                            f"Timestamp: {alert.get('timestamp', '')}"
                        )}]
                    }]
                },
                "issuetype": {"name": config.get("jira_issue_type", "Bug")},
                "priority": {"name": JIRA_PRIORITY_MAP.get(severity, "Medium")},
            }
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{jira_url}/rest/api/3/issue", json=payload, headers=headers)
            data = resp.json()
            ticket_key = data.get("key")
            if ticket_key:
                await _store_ticket(alert.get("alert_id"), "jira", ticket_key, f"{jira_url}/browse/{ticket_key}")
                return {"success": True, "ticket_key": ticket_key, "url": f"{jira_url}/browse/{ticket_key}"}
            return {"success": False, "error": str(data)}
    except Exception as e:
        logger.error(f"Jira ticket creation failed: {e}")
        return {"success": False, "error": str(e)}


# ─── Zoho Desk ───────────────────────────────────────────────────────────────

async def create_zoho_desk_ticket(alert: dict, config: dict) -> dict:
    """Create a Zoho Desk ticket from a platform alert."""
    try:
        import httpx
        org_id = config.get("zoho_org_id")
        token = config.get("zoho_token")
        dept_id = config.get("zoho_department_id")
        
        if not all([org_id, token, dept_id]):
            return {"success": False, "error": "Missing Zoho Desk configuration (org_id, department_id, or token)"}

        severity = alert.get("severity", "medium").lower()
        payload = {
            "subject": f"[{severity.upper()}] {alert.get('type', 'Security Alert').replace('_', ' ')}",
            "departmentId": dept_id,
            "description": (
                f"Alert ID: {alert.get('alert_id', 'N/A')}\n"
                f"Hostname: {alert.get('hostname', 'Unknown')}\n"
                f"Description: {alert.get('description', '')}\n"
                f"Process: {alert.get('process', {}).get('name', 'N/A')}\n"
                f"MITRE: {alert.get('mitre_technique', 'N/A')}"
            ),
            "priority": {"critical": "High", "high": "High", "medium": "Medium", "low": "Low"}.get(severity, "Medium"),
            "category": "Security Incident"
        }
        
        headers = {
            "Authorization": f"Zoho-oauthtoken {token}",
            "orgId": org_id,
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post("https://desk.zoho.com/api/v1/tickets", json=payload, headers=headers)
            data = resp.json()
            ticket_id = data.get("id")
            if ticket_id:
                ticket_number = data.get("ticketNumber", ticket_id)
                ticket_url = f"https://desk.zoho.com/support/yourorg/ShowTicket.do?id={ticket_id}" # Simplified URL
                await _store_ticket(alert.get("alert_id"), "zoho", ticket_number, ticket_url)
                return {"success": True, "ticket_number": ticket_number, "url": ticket_url}
            return {"success": False, "error": str(data)}
    except Exception as e:
        logger.error(f"Zoho Desk ticket creation failed: {e}")
        return {"success": False, "error": str(e)}


# ─── Custom Webhook ───────────────────────────────────────────────────────────

async def create_custom_webhook_ticket(alert: dict, config: dict) -> dict:
    """Send alert data to a custom webhook (generic integration)."""
    try:
        import httpx, json
        url = config.get("custom_webhook_url")
        method = config.get("custom_webhook_method", "POST").upper()
        headers = config.get("custom_webhook_headers", {})
        payload_template = config.get("custom_webhook_payload", {})
        
        if not url:
            return {"success": False, "error": "Missing Custom Webhook URL"}

        # Basic template substitution (alert fields)
        def _subst(val):
            if isinstance(val, str) and val.startswith("{{") and val.endswith("}}"):
                key = val[2:-2].strip()
                return alert.get(key, val)
            if isinstance(val, dict):
                return {k: _subst(v) for k, v in val.items()}
            return val

        payload = _subst(payload_template) if payload_template else alert
        
        async with httpx.AsyncClient(timeout=10) as client:
            if method == "POST":
                resp = await client.post(url, json=payload, headers=headers)
            elif method == "PUT":
                resp = await client.put(url, json=payload, headers=headers)
            else:
                return {"success": False, "error": f"Unsupported method: {method}"}
                
            return {"success": resp.status_code in (200, 201, 202), "status": resp.status_code}
    except Exception as e:
        logger.error(f"Custom Webhook failed: {e}")
        return {"success": False, "error": str(e)}

async def create_servicenow_incident(alert: dict, config: dict) -> dict:
    """Create a ServiceNow incident from a platform alert."""
    try:
        import httpx
        instance = config.get("snow_instance", "").rstrip("/")
        severity = alert.get("severity", "medium").lower()
        payload = {
            "short_description": f"[{severity.upper()}] {alert.get('type', 'Alert').replace('_', ' ')} on {alert.get('hostname', 'Unknown')}",
            "description": (
                f"Alert ID: {alert.get('alert_id', '')}\n"
                f"Description: {alert.get('description', '')}\n"
                f"Process: {alert.get('process', {}).get('name', 'N/A')}\n"
                f"SHA256: {alert.get('process', {}).get('sha256', 'N/A')}\n"
                f"MITRE Technique: {alert.get('mitre_technique', 'N/A')}"
            ),
            "urgency": str(SNOW_URGENCY_MAP.get(severity, 3)),
            "impact": str(SNOW_URGENCY_MAP.get(severity, 3)),
            "category": "Security",
            "subcategory": "Intrusion",
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"https://{instance}.service-now.com/api/now/table/incident",
                json=payload,
                auth=(config.get("snow_username"), config.get("snow_password")),
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
            data = resp.json().get("result", {})
            sys_id = data.get("sys_id")
            ticket_url = f"https://{instance}.service-now.com/incident.do?sys_id={sys_id}"
            if sys_id:
                await _store_ticket(alert.get("alert_id"), "servicenow", data.get("number"), ticket_url)
                return {"success": True, "ticket_number": data.get("number"), "url": ticket_url}
            return {"success": False, "error": str(data)}
    except Exception as e:
        logger.error(f"ServiceNow incident creation failed: {e}")
        return {"success": False, "error": str(e)}


# ─── PagerDuty ────────────────────────────────────────────────────────────────

async def send_pagerduty_alert(alert: dict, routing_key: str) -> dict:
    """Send a PagerDuty Events API v2 alert."""
    try:
        import httpx
        severity = alert.get("severity", "warning").lower()
        pd_severity = {"critical": "critical", "high": "error", "medium": "warning", "low": "info"}.get(severity, "warning")
        payload = {
            "routing_key": routing_key,
            "event_action": "trigger",
            "dedup_key": alert.get("alert_id", str(uuid.uuid4())),
            "payload": {
                "summary": f"[{severity.upper()}] {alert.get('description', 'Security Alert')}",
                "severity": pd_severity,
                "source": alert.get("hostname", "unknown"),
                "timestamp": alert.get("timestamp", datetime.now(timezone.utc).isoformat()),
                "custom_details": {
                    "alert_id": alert.get("alert_id"),
                    "process": alert.get("process", {}).get("name"),
                    "mitre_technique": alert.get("mitre_technique"),
                },
            },
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post("https://events.pagerduty.com/v2/enqueue", json=payload)
            return {"success": resp.status_code in (200, 202), "status_code": resp.status_code}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Slack / Teams ────────────────────────────────────────────────────────────

async def send_slack_alert(alert: dict, webhook_url: str) -> dict:
    """Send a rich Slack Block Kit message to the security channel."""
    try:
        import httpx
        severity = alert.get("severity", "medium").lower()
        color = {"critical": "#ef4444", "high": "#f97316", "medium": "#eab308", "low": "#22c55e"}.get(severity, "#6366f1")
        payload = {
            "attachments": [{
                "color": color,
                "blocks": [
                    {"type": "header", "text": {"type": "plain_text", "text": f"🚨 {severity.upper()} Alert: {alert.get('type', '').replace('_', ' ')}"}},
                    {"type": "section", "fields": [
                        {"type": "mrkdwn", "text": f"*Host:*\n{alert.get('hostname', 'Unknown')}"},
                        {"type": "mrkdwn", "text": f"*Process:*\n{alert.get('process', {}).get('name', 'N/A')}"},
                        {"type": "mrkdwn", "text": f"*MITRE:*\n{alert.get('mitre_technique', 'N/A')}"},
                        {"type": "mrkdwn", "text": f"*Alert ID:*\n{alert.get('alert_id', 'N/A')}"},
                    ]},
                    {"type": "section", "text": {"type": "mrkdwn", "text": f"_{alert.get('description', '')}_"}},
                ],
            }]
        }
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.post(webhook_url, json=payload)
            return {"success": resp.status_code == 200}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def send_teams_alert(alert: dict, webhook_url: str) -> dict:
    """Send a Microsoft Teams Adaptive Card alert."""
    try:
        import httpx
        severity = alert.get("severity", "medium").lower()
        color = {"critical": "attention", "high": "warning", "medium": "accent", "low": "good"}.get(severity, "default")
        payload = {
            "type": "message",
            "attachments": [{
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard", "version": "1.4",
                    "body": [
                        {"type": "TextBlock", "size": "Large", "weight": "Bolder",
                         "text": f"🚨 {severity.upper()}: {alert.get('type', '').replace('_', ' ')}", "color": color},
                        {"type": "FactSet", "facts": [
                            {"title": "Host", "value": alert.get("hostname", "N/A")},
                            {"title": "Process", "value": alert.get("process", {}).get("name", "N/A")},
                            {"title": "MITRE Technique", "value": alert.get("mitre_technique", "N/A")},
                            {"title": "Alert ID", "value": alert.get("alert_id", "N/A")},
                        ]},
                        {"type": "TextBlock", "text": alert.get("description", ""), "wrap": True},
                    ],
                },
            }]
        }
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.post(webhook_url, json=payload)
            return {"success": resp.status_code == 200}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Auto-Dispatch (called from alert endpoints) ──────────────────────────────

async def auto_create_ticket_for_alert(alert: dict, tenant_id: str):
    """Called automatically when a new alert is stored, if auto-ticketing is configured."""
    config = await get_ticketing_config(tenant_id)
    if not config:
        return

    severity = alert.get("severity", "info").lower()
    auto_severities = config.get("auto_create_severity", ["critical"])
    if severity not in auto_severities:
        return

    if config.get("provider") == "jira":
        await create_jira_ticket(alert, config)
    elif config.get("provider") == "servicenow":
        await create_servicenow_incident(alert, config)
    elif config.get("provider") == "zoho":
        await create_zoho_desk_ticket(alert, config)
    elif config.get("provider") == "custom":
        await create_custom_webhook_ticket(alert, config)


# ─── Storage ─────────────────────────────────────────────────────────────────

async def _store_ticket(alert_id: str, provider: str, ticket_ref: str, url: str):
    db = get_database()
    await db.ticketing_log.insert_one({
        "alert_id": alert_id,
        "provider": provider,
        "ticket_ref": ticket_ref,
        "url": url,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


async def list_tickets(tenant_id: str, limit: int = 50) -> list:
    db = get_database()
    docs = await db.ticketing_log.find().sort("created_at", -1).limit(limit).to_list(limit)
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs
