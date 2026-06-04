"""
Google Cloud Security Command Center (SCC) SIEM Ingest
Polls GCP SCC findings and Chronicle SIEM events, ingesting them into security_events.
Falls back gracefully when google-cloud-securitycenter is not installed or credentials missing.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from database import get_database

logger = logging.getLogger(__name__)

try:
    from google.cloud import securitycenter
    from google.oauth2 import service_account
    _GCP_SDK_AVAILABLE = True
except ImportError:
    _GCP_SDK_AVAILABLE = False
    logger.warning("[GCPSCC] google-cloud-securitycenter not installed — GCP SCC ingest disabled")


def _make_scc_client(service_account_json: str) -> Optional[Any]:
    if not _GCP_SDK_AVAILABLE:
        return None
    try:
        sa_info = json.loads(service_account_json) if isinstance(service_account_json, str) else service_account_json
        credentials = service_account.Credentials.from_service_account_info(
            sa_info,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        return securitycenter.SecurityCenterClient(credentials=credentials)
    except Exception as exc:
        logger.error("[GCPSCC] Failed to build SCC client: %s", exc)
        return None


def _severity_map(gcp_severity: str) -> str:
    return {
        "CRITICAL": "Critical",
        "HIGH": "High",
        "MEDIUM": "Medium",
        "LOW": "Low",
        "SEVERITY_UNSPECIFIED": "Low",
    }.get(gcp_severity.upper() if gcp_severity else "", "Medium")


def _parse_scc_finding(finding: Any, tenant_id: str) -> Dict[str, Any]:
    if isinstance(finding, dict):
        name = finding.get("name", "")
        category = finding.get("category", "")
        resource_name = finding.get("resourceName", "")
        severity = _severity_map(finding.get("severity", ""))
        state = finding.get("state", "ACTIVE")
        description = finding.get("description", "")
        event_time = finding.get("eventTime", datetime.now(timezone.utc).isoformat())
        source_props = finding.get("sourceProperties", {})
    else:
        name = getattr(finding, "name", "")
        category = getattr(finding, "category", "")
        resource_name = getattr(finding, "resource_name", "")
        sev = getattr(finding, "severity", None)
        severity = _severity_map(str(sev) if sev is not None else "")
        state = str(getattr(finding, "state", "ACTIVE"))
        description = getattr(finding, "description", "")
        event_time = getattr(finding, "event_time", None)
        if event_time and hasattr(event_time, "isoformat"):
            event_time = event_time.isoformat()
        elif not event_time:
            event_time = datetime.now(timezone.utc).isoformat()
        source_props = {}

    return {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "timestamp": str(event_time),
        "log_type": "gcp_scc",
        "title": category,
        "description": description or f"GCP SCC finding: {category}",
        "severity": severity,
        "status": "Active" if "ACTIVE" in str(state) else "Resolved",
        "resource_name": resource_name,
        "finding_name": name,
        "source_properties": source_props,
        "raw_message": f"[GCP SCC] {category} on {resource_name}",
        "source": "gcp_security_command_center",
    }


async def poll_gcp_scc_findings(config: Dict[str, Any], omni_tenant_id: str) -> int:
    """
    Poll GCP Security Command Center findings for a configured integration.
    Returns count of new events ingested.
    """
    if not _GCP_SDK_AVAILABLE:
        logger.debug("[GCPSCC] SDK unavailable, skipping poll")
        return 0

    sa_json = config.get("service_account_json", "")
    organization_id = config.get("organization_id", "")
    project_id = config.get("project_id", "")

    if not sa_json:
        logger.warning("[GCPSCC] No service account JSON for tenant %s", omni_tenant_id)
        return 0

    parent = (
        f"organizations/{organization_id}"
        if organization_id
        else f"projects/{project_id}"
        if project_id
        else ""
    )
    if not parent:
        logger.warning("[GCPSCC] No organization_id or project_id for tenant %s", omni_tenant_id)
        return 0

    try:
        client = _make_scc_client(sa_json)
        if not client:
            return 0

        request = securitycenter.ListFindingsRequest(
            parent=f"{parent}/sources/-",
            filter='state="ACTIVE"',
            page_size=200,
        )
        response = client.list_findings(request=request)

        events = []
        for result in response:
            finding = result.finding if hasattr(result, "finding") else result
            events.append(_parse_scc_finding(finding, omni_tenant_id))

        if not events:
            logger.info("[GCPSCC] No findings for %s / tenant %s", parent, omni_tenant_id)
            return 0

        db = get_database()
        await db.security_events.insert_many(events)
        logger.info("[GCPSCC] Ingested %d findings for tenant %s", len(events), omni_tenant_id)
        return len(events)

    except Exception as exc:
        logger.error("[GCPSCC] Poll failed for tenant %s: %s", omni_tenant_id, exc)
        return 0


async def poll_gcp_chronicle(config: Dict[str, Any], omni_tenant_id: str) -> int:
    """
    Poll Google Chronicle SIEM via REST API.
    Uses service account OAuth2 to authenticate.
    """
    try:
        import google.auth.transport.requests as _gtr
        from google.oauth2 import service_account as _sa
        import urllib.request as _ur
    except ImportError:
        logger.debug("[Chronicle] google-auth not installed, skipping")
        return 0

    sa_json = config.get("service_account_json", "")
    chronicle_region = config.get("chronicle_region", "us")
    if not sa_json:
        return 0

    try:
        sa_info = json.loads(sa_json) if isinstance(sa_json, str) else sa_json
        credentials = _sa.Credentials.from_service_account_info(
            sa_info,
            scopes=["https://www.googleapis.com/auth/chronicle-backstory"],
        )
        credentials.refresh(_gtr.Request())
        token = credentials.token

        base_url = f"https://{chronicle_region}-backstory.googleapis.com/v1"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        import urllib.request
        import json as _json

        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=1)
        url = f"{base_url}/detect/alerts?start_time={start_time.strftime('%Y-%m-%dT%H:%M:%SZ')}&end_time={end_time.strftime('%Y-%m-%dT%H:%M:%SZ')}&page_size=200"

        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = _json.loads(resp.read())

        alerts = data.get("alerts", [])
        db = get_database()
        events = []
        for alert in alerts:
            events.append({
                "id": str(uuid.uuid4()),
                "tenant_id": omni_tenant_id,
                "timestamp": alert.get("createdTime", datetime.now(timezone.utc).isoformat()),
                "log_type": "gcp_chronicle",
                "title": alert.get("ruleName", "Chronicle Alert"),
                "description": alert.get("alertState", ""),
                "severity": "High",
                "status": "Active",
                "raw_message": f"[Chronicle] {alert.get('ruleName', '')}",
                "source": "gcp_chronicle",
            })

        if events:
            await db.security_events.insert_many(events)
            logger.info("[Chronicle] Ingested %d alerts for tenant %s", len(events), omni_tenant_id)

        return len(events)

    except Exception as exc:
        logger.error("[Chronicle] Poll failed for tenant %s: %s", omni_tenant_id, exc)
        return 0


# ── Background polling loop ────────────────────────────────────────────────────

async def start_gcp_polling():
    """Background loop: poll all GCP-configured tenants every 5 minutes."""
    logger.info("[GCPSCC] Background polling loop started")
    while True:
        try:
            await asyncio.sleep(300)
            db = get_database()
            integrations = await db.cloud_integrations.find(
                {"provider": {"$in": ["gcp_scc", "gcp_chronicle"]}, "enabled": True}
            ).to_list(length=100)

            for integ in integrations:
                tenant_id = integ.get("tenant_id") or None
                if not tenant_id:
                    logger.warning("[GCPSCC] Skipping integration %s — no tenant_id configured", integ.get("id", "?"))
                    continue
                provider = integ.get("provider", "")
                cfg = integ.get("config", {})

                if provider == "gcp_scc":
                    await poll_gcp_scc_findings(cfg, tenant_id)
                elif provider == "gcp_chronicle":
                    await poll_gcp_chronicle(cfg, tenant_id)

        except Exception as exc:
            logger.error("[GCPSCC] Polling loop error: %s", exc)
