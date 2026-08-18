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
from collections import namedtuple
from typing import Any, Dict, Optional

from itam_webhook_events import EVENT_ASSET_AUDIT_OVERDUE
from ticketing_service import (
    get_ticketing_config,
    create_jira_ticket,
    create_servicenow_incident,
)

logger = logging.getLogger(__name__)


# ─── ITAM entity → collection mapping (Phase 73 Plan 04, D-09/D-10) ────────

# (collection name, id field name, tenant field name). The tenant-field
# divergence encoded here is real and verified: `assets` docs use the
# camelCase `tenantId`, `asset_requests` docs use the snake_case
# `tenant_id` — a single shared filter shape would silently write to
# nothing for one of the two collections.
_EntityCollectionInfo = namedtuple(
    "_EntityCollectionInfo", ["collection", "id_field", "tenant_field"]
)

ITAM_ENTITY_COLLECTIONS = {
    "asset": _EntityCollectionInfo("assets", "id", "tenantId"),
    "asset_request": _EntityCollectionInfo("asset_requests", "id", "tenant_id"),
}

# Event type used when an operator requests a ticket manually (D-10), with
# no originating webhook event to derive `type`/`alert_id` from.
ITAM_TICKET_EVENT_MANUAL = "manual"

# Severity → connector-accepted word, keyed by ITAM event type. ITAM
# entities carry no severity field of their own — never read one off the
# entity, always resolve it here, defaulting to "medium".
_ITAM_EVENT_SEVERITY = {
    EVENT_ASSET_AUDIT_OVERDUE: "medium",
}

_ITAM_UNKNOWN_ASSET_PLACEHOLDER = "Unknown Asset"


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


async def _itam_event_to_alert_shape(db, event_type: str, entity_kind: str, entity: dict) -> dict:
    """ITAM sibling of `_task_to_alert_shape` — adapts an ITAM asset or asset
    request into the identical alert shape both `create_jira_ticket` and
    `create_servicenow_incident` consume unchanged (D-09).

    May be called from a background sweep with no ambient tenant context
    (plan 73-05's automatic triggers), so every database read this function
    performs must be scoped by the caller-supplied tenant value, never by
    ambient request context. This first cut performs no database reads at
    all — everything is derived from the entity dict already passed in.
    """
    entity_id = entity.get("id", "")

    if event_type == ITAM_TICKET_EVENT_MANUAL:
        alert_type = "itam_manual_ticket"
    else:
        alert_type = f"itam_{event_type.replace('.', '_')}"

    alert_id = f"itam-{event_type.replace('.', '-')}-{entity_id}"
    severity = _ITAM_EVENT_SEVERITY.get(event_type, "medium")

    if entity_kind == "asset":
        hostname = _ITAM_UNKNOWN_ASSET_PLACEHOLDER
        try:
            hostname = entity.get("hostname") or entity.get("assetTag") or _ITAM_UNKNOWN_ASSET_PLACEHOLDER
        except Exception:
            pass  # best-effort; hostname stays the placeholder, never raises

        if event_type == EVENT_ASSET_AUDIT_OVERDUE:
            reason = "An asset is overdue for its physical audit."
        elif event_type == ITAM_TICKET_EVENT_MANUAL:
            reason = "An operator requested a ticket manually for this asset."
        else:
            reason = "An ITAM condition on this asset requires attention."
        description = (
            f"{reason}\n\n"
            f"Asset Tag: {entity.get('assetTag', 'N/A')}\n"
            f"Hostname: {hostname}"
        )
        timestamp = entity.get("updatedAt") or entity.get("createdAt") or ""
    else:
        # entity kind "asset_request" — never attempt an asset lookup here.
        item_description = entity.get("item_description") or ""
        hostname = item_description or _ITAM_UNKNOWN_ASSET_PLACEHOLDER

        if event_type == ITAM_TICKET_EVENT_MANUAL:
            reason = "An operator requested a ticket manually for this asset request."
        else:
            reason = "An asset request has been pending approval beyond the escalation window."
        description = (
            f"{reason}\n\n"
            f"Item: {item_description}\n"
            f"Quantity: {entity.get('quantity', 'N/A')}\n"
            f"Requester: {entity.get('requester_id', 'N/A')}"
        )
        timestamp = entity.get("request_date") or ""

    if hasattr(timestamp, "isoformat"):
        timestamp = timestamp.isoformat()
    elif timestamp:
        timestamp = str(timestamp)
    else:
        timestamp = ""

    return {
        "alert_id": alert_id,
        "type": alert_type,
        "severity": severity,
        "hostname": hostname,
        "process": {},
        "mitre_technique": "N/A",
        "description": description,
        "timestamp": timestamp,
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


# ─── Close-loop scheduler ────────────────────────────────────────────────────

async def run_close_loop_pass(db) -> None:
    """One polling sweep: for every open/in_progress task with a linked
    ticket, check the ticket's external status and resolve the task via
    compliance_remediation_service.update_task when it has closed — this
    reuse is what makes REM-02's re-scan dispatch fire by construction.
    A deleted (404) ticket is logged and skipped, never auto-resolved on
    ambiguous evidence (D-06). The whole pass is non-fatal."""
    try:
        query = {
            "status": {"$in": ["open", "in_progress"]},
            "ticket_ref": {"$ne": None},
        }
        cursor = db.compliance_remediation_tasks.find(query, {"_id": 0})
        async for task in cursor:
            tenant_id = task.get("tenantId", "")
            config = await get_ticketing_config(tenant_id)
            if not config:
                continue  # ticketing config removed after ticket creation

            provider = task.get("ticket_provider")
            if provider == "jira":
                result = await get_jira_issue_status(task["ticket_ref"], config)
            elif provider == "servicenow":
                result = await get_servicenow_incident_status(task["ticket_ref"], config)
            else:
                continue

            if result.get("not_found"):
                logger.info(
                    "Close-loop: ticket %s for task %s not found (deleted?) — "
                    "skipped, not auto-resolved",
                    task.get("ticket_ref"), task["id"],
                )
                continue

            if result.get("closed"):
                import compliance_remediation_service as svc
                updated = await svc.update_task(
                    db, task["id"], {"status": "resolved"},
                    {"tenantId": tenant_id}, created_by="system:ticket-close-loop",
                )
                if updated:
                    try:
                        from websocket_manager import broadcast_remediation_update
                        await broadcast_remediation_update(tenant_id, {
                            "task_id": task["id"], "status": "resolved",
                            "control_id": updated.get("control_id"),
                        })
                    except Exception:
                        pass  # best-effort broadcast — non-fatal
    except Exception as exc:
        logger.error("Close-loop pass failed: %s", exc)


async def start_close_loop_scheduler(db) -> None:
    """Loop every 5 minutes running the close-loop pass (D-03, revised
    2026-07-21). Must receive db as a passed-in raw parameter — see module
    docstring."""
    logger.info("Ticketing close-loop scheduler started (interval=300s)")
    while True:
        await run_close_loop_pass(db)
        await asyncio.sleep(300)
