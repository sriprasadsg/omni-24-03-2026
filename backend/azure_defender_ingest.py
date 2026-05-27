"""
Azure Defender for Cloud / Microsoft Sentinel SIEM Ingest
Polls Azure Security Center alerts and ingests them into security_events.
Falls back gracefully when azure-mgmt-security is not installed or credentials missing.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from database import get_database

logger = logging.getLogger(__name__)

try:
    from azure.identity import ClientSecretCredential
    from azure.mgmt.security import SecurityCenter
    _AZURE_SDK_AVAILABLE = True
except ImportError:
    _AZURE_SDK_AVAILABLE = False
    logger.warning("[AzureDefender] azure-mgmt-security not installed — Azure Defender ingest disabled")


def _make_azure_client(tenant_id: str, client_id: str, client_secret: str, subscription_id: str):
    if not _AZURE_SDK_AVAILABLE:
        return None, None
    credential = ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
    )
    client = SecurityCenter(credential, subscription_id)
    return client, subscription_id


def _severity_map(azure_severity: str) -> str:
    return {
        "High": "Critical",
        "Medium": "High",
        "Low": "Medium",
        "Informational": "Low",
    }.get(azure_severity, "Medium")


def _parse_defender_alert(alert: Any, tenant_id: str) -> Dict[str, Any]:
    props = getattr(alert, "properties", alert) if not isinstance(alert, dict) else alert
    if isinstance(props, dict):
        alert_type = props.get("alertType", "")
        alert_name = props.get("alertDisplayName", alert_type)
        description = props.get("description", "")
        severity = _severity_map(props.get("severity", "Medium"))
        status = props.get("status", "Active")
        compromised_entity = props.get("compromisedEntity", "")
        time_generated = props.get("timeGeneratedUtc", datetime.now(timezone.utc).isoformat())
        resource_id = props.get("resourceIdentifiers", [{}])
        remote_address = props.get("remoteAddress", "")
    else:
        alert_type = getattr(props, "alert_type", "")
        alert_name = getattr(props, "alert_display_name", alert_type)
        description = getattr(props, "description", "")
        severity = _severity_map(getattr(props, "severity", "Medium"))
        status = getattr(props, "status", "Active")
        compromised_entity = getattr(props, "compromised_entity", "")
        time_generated = getattr(props, "time_generated_utc", datetime.now(timezone.utc).isoformat())
        if hasattr(time_generated, "isoformat"):
            time_generated = time_generated.isoformat()
        resource_id = []
        remote_address = ""

    return {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "timestamp": time_generated,
        "log_type": "azure_defender",
        "alert_type": alert_type,
        "title": alert_name,
        "description": description,
        "severity": severity,
        "status": status,
        "compromised_entity": compromised_entity,
        "remote_address": remote_address,
        "resource_identifiers": resource_id,
        "raw_message": f"[Azure Defender] {alert_name}: {description[:200]}",
        "source": "azure_defender_for_cloud",
    }


async def poll_azure_defender_alerts(config: Dict[str, Any], omni_tenant_id: str) -> int:
    """
    Poll Azure Defender for Cloud alerts for a configured integration.
    Returns count of new events ingested.
    """
    if not _AZURE_SDK_AVAILABLE:
        logger.debug("[AzureDefender] SDK unavailable, skipping poll")
        return 0

    az_tenant = config.get("azure_tenant_id", "")
    client_id = config.get("client_id", "")
    client_secret = config.get("client_secret", "")
    subscription_id = config.get("subscription_id", "")

    if not all([az_tenant, client_id, client_secret, subscription_id]):
        logger.warning("[AzureDefender] Incomplete credentials for tenant %s", omni_tenant_id)
        return 0

    try:
        client, sub_id = _make_azure_client(az_tenant, client_id, client_secret, subscription_id)
        if not client:
            return 0

        alerts = list(client.alerts.list())
        if not alerts:
            logger.info("[AzureDefender] No alerts returned for subscription %s", subscription_id)
            return 0

        db = get_database()
        events = [_parse_defender_alert(a, omni_tenant_id) for a in alerts]

        if events:
            await db.security_events.insert_many(events)
            logger.info("[AzureDefender] Ingested %d alerts for tenant %s", len(events), omni_tenant_id)

        return len(events)

    except Exception as exc:
        logger.error("[AzureDefender] Poll failed for tenant %s: %s", omni_tenant_id, exc)
        return 0


async def poll_sentinel_logs(config: Dict[str, Any], omni_tenant_id: str) -> int:
    """
    Poll Microsoft Sentinel workspace logs via Azure Monitor / Log Analytics API.
    Requires azure-monitor-query SDK.
    """
    try:
        from azure.identity import ClientSecretCredential as _Cred
        from azure.monitor.query import LogsQueryClient, LogsQueryStatus
    except ImportError:
        logger.debug("[Sentinel] azure-monitor-query not installed, skipping")
        return 0

    workspace_id = config.get("sentinel_workspace_id", "")
    az_tenant = config.get("azure_tenant_id", "")
    client_id = config.get("client_id", "")
    client_secret = config.get("client_secret", "")

    if not all([workspace_id, az_tenant, client_id, client_secret]):
        return 0

    try:
        cred = _Cred(tenant_id=az_tenant, client_id=client_id, client_secret=client_secret)
        logs_client = LogsQueryClient(cred)

        query = (
            "SecurityAlert "
            "| where TimeGenerated > ago(1h) "
            "| project TimeGenerated, AlertName, Description, Severity, Status, CompromisedEntity "
            "| limit 200"
        )
        response = logs_client.query_workspace(workspace_id, query, timespan=timedelta(hours=1))

        if response.status != LogsQueryStatus.SUCCESS:
            logger.warning("[Sentinel] Query returned non-success status: %s", response.status)
            return 0

        db = get_database()
        events = []
        for table in response.tables:
            cols = table.columns
            for row in table.rows:
                row_dict = dict(zip(cols, row))
                events.append({
                    "id": str(uuid.uuid4()),
                    "tenant_id": omni_tenant_id,
                    "timestamp": str(row_dict.get("TimeGenerated", datetime.now(timezone.utc).isoformat())),
                    "log_type": "microsoft_sentinel",
                    "title": row_dict.get("AlertName", ""),
                    "description": row_dict.get("Description", ""),
                    "severity": _severity_map(str(row_dict.get("Severity", "Medium"))),
                    "status": row_dict.get("Status", "Active"),
                    "compromised_entity": row_dict.get("CompromisedEntity", ""),
                    "raw_message": f"[Sentinel] {row_dict.get('AlertName', '')}",
                    "source": "microsoft_sentinel",
                })

        if events:
            await db.security_events.insert_many(events)
            logger.info("[Sentinel] Ingested %d events for tenant %s", len(events), omni_tenant_id)

        return len(events)

    except Exception as exc:
        logger.error("[Sentinel] Poll failed for tenant %s: %s", omni_tenant_id, exc)
        return 0


# ── Background polling loop ────────────────────────────────────────────────────

async def start_azure_polling():
    """Background loop: poll all Azure-configured tenants every 5 minutes."""
    logger.info("[AzureDefender] Background polling loop started")
    while True:
        try:
            await asyncio.sleep(300)
            db = get_database()
            integrations = await db.cloud_integrations.find(
                {"provider": {"$in": ["azure_defender", "microsoft_sentinel"]}, "enabled": True}
            ).to_list(length=100)

            for integ in integrations:
                tenant_id = integ.get("tenant_id") or None
                if not tenant_id:
                    logger.warning("[AzureDefender] Skipping integration %s — no tenant_id configured", integ.get("id", "?"))
                    continue
                provider = integ.get("provider", "")
                cfg = integ.get("config", {})

                if provider == "azure_defender":
                    await poll_azure_defender_alerts(cfg, tenant_id)
                elif provider == "microsoft_sentinel":
                    await poll_sentinel_logs(cfg, tenant_id)

        except Exception as exc:
            logger.error("[AzureDefender] Polling loop error: %s", exc)
