"""
Remediation-to-Ticketing Bridge
--------------------------------
Wires `compliance_remediation_tasks` to the existing Jira/ServiceNow connectors
in `ticketing_service.py` through an explicit field adapter (REM-01), plus the
external-ticket status-poll functions and the close-loop scheduler that
auto-resolves a task when its linked ticket closes (REM-02).

Scheduler functions in this module receive `db` as a raw parameter and never
resolve the database handle themselves — `compliance_remediation_tasks` is
not in `database.py`'s tenant-isolation exemption allowlist, so it is wrapped
by `TenantIsolatedDatabase`, which resolves the tenant from request-context.
A bare `asyncio.create_task()` scheduler has no request context, so calling
the request-scoped database accessor here would silently fail closed.
"""
import asyncio
import logging
from typing import Any, Dict, Optional

from ticketing_service import (
    get_ticketing_config,
    create_jira_ticket,
    create_servicenow_incident,
)

logger = logging.getLogger(__name__)


# ─── Adapter ───────────────────────────────────────────────────────────────

async def _task_to_alert_shape(db, task: dict) -> dict:
    """Adapt a compliance_remediation_tasks doc into the alert-shaped dict
    ticketing_service.py's connectors expect."""
    hostname = "Unknown"
    asset_id = task.get("asset_id")
    if asset_id:
        try:
            asset = await db.assets.find_one({"id": asset_id})
            hostname = (asset or {}).get("hostname", "Unknown")
        except Exception:
            pass  # best-effort; hostname stays "Unknown", never raises
    return {
        "alert_id": task["id"],
        "type": "compliance_remediation",
        "severity": task.get("priority", "medium"),
        "hostname": hostname,
        "process": {},
        "mitre_technique": "N/A",
        "description": (
            f"Compliance control {task.get('control_id', 'N/A')} failed "
            f"(framework: {task.get('framework_id', 'N/A')}).\n\n"
            f"{task.get('description', '')}"
        ),
        "timestamp": task.get("created_at", ""),
    }


# ─── Ticket-creation orchestration ──────────────────────────────────────────

async def create_ticket_for_remediation_task(
    db, task: dict, tenant_id: str, provider_override: Optional[str] = None,
) -> Optional[dict]:
    """Manual + auto-create entry point: creates a Jira/ServiceNow ticket for
    a remediation task and $set-persists ticket_provider/ticket_ref/ticket_url
    onto the task. Non-fatal on failure — returns None, never raises."""
    if task.get("ticket_ref"):
        return None  # dedup guard — a task with a ticket never gets a second one

    config = await get_ticketing_config(tenant_id)
    if not config:
        return None  # no-op when ticketing is not configured for the tenant

    provider = provider_override or config.get("provider")
    alert = await _task_to_alert_shape(db, task)

    if provider == "jira":
        result = await create_jira_ticket(alert, config)
        ref, url = result.get("ticket_key"), result.get("url")
    elif provider == "servicenow":
        result = await create_servicenow_incident(alert, config)
        ref, url = result.get("ticket_number"), result.get("url")
    else:
        return None

    if result.get("success") and ref:
        await db.compliance_remediation_tasks.update_one(
            {"id": task["id"], "tenantId": tenant_id},
            {"$set": {"ticket_provider": provider, "ticket_ref": ref, "ticket_url": url}},
        )
        return {"ticket_provider": provider, "ticket_ref": ref, "ticket_url": url}
    return None  # non-fatal — caller handles toast/log


# ─── External-ticket status checks ─────────────────────────────────────────

async def get_jira_issue_status(ticket_key: str, config: dict) -> dict:
    """Classify a Jira issue as closed/open via statusCategory.key — never
    string-match on status.name. Returns not_found:True on a 404 (deleted
    or unknown issue) so the caller can skip, not auto-resolve."""
    import httpx
    import base64
    jira_url = config.get("jira_url", "").rstrip("/")
    auth = base64.b64encode(
        f"{config['jira_email']}:{config['jira_api_token']}".encode()
    ).decode()
    headers = {"Authorization": f"Basic {auth}", "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{jira_url}/rest/api/3/issue/{ticket_key}?fields=status", headers=headers,
            )
            if resp.status_code == 404:
                logger.warning(
                    "Ticket %s not found (deleted?) — skipping close-loop resolution", ticket_key,
                )
                return {"success": False, "closed": False, "not_found": True}
            data = resp.json()
            category = data.get("fields", {}).get("status", {}).get("statusCategory", {}).get("key", "")
            return {"success": True, "closed": category == "done"}
    except Exception as e:
        return {"success": False, "closed": False, "error": str(e)}


_SNOW_CLOSED_LABELS = {"closed", "resolved"}


async def get_servicenow_incident_status(sys_id: str, config: dict) -> dict:
    """Classify a ServiceNow incident as closed/open via the display-value
    label, comparing against _SNOW_CLOSED_LABELS — never hardcode numeric
    state codes (instance-customizable). Returns not_found:True on a 404
    (deleted or unknown sys_id) so the caller can skip, not auto-resolve."""
    import httpx
    instance = config.get("snow_instance", "").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"https://{instance}.service-now.com/api/now/table/incident/{sys_id}"
                f"?sysparm_fields=state&sysparm_display_value=true",
                auth=(config.get("snow_username"), config.get("snow_password")),
                headers={"Accept": "application/json"},
            )
            if resp.status_code == 404:
                logger.warning(
                    "Ticket %s not found (deleted?) — skipping close-loop resolution", sys_id,
                )
                return {"success": False, "closed": False, "not_found": True}
            data = resp.json().get("result", {})
            state_label = str(data.get("state", "")).strip().lower()
            return {"success": True, "closed": state_label in _SNOW_CLOSED_LABELS}
    except Exception as e:
        return {"success": False, "closed": False, "error": str(e)}
