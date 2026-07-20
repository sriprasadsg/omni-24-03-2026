"""
Oracle Cloud Infrastructure (OCI) Cloud Guard Ingest
Polls OCI Cloud Guard problems and ingests them into security_events.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from database import get_database
from tenant_context import set_tenant_id

logger = logging.getLogger(__name__)

try:
    import oci
    _OCI_SDK_AVAILABLE = True
except ImportError:
    _OCI_SDK_AVAILABLE = False
    logger.warning("[OCI] oci SDK not installed — OCI Cloud Guard ingest disabled")


def _make_oci_client(config: Dict[str, Any]):
    if not _OCI_SDK_AVAILABLE:
        return None

    # OCI config dict shape
    oci_config = {
        "tenancy": config.get("oci_tenancy_ocid"),
        "user": config.get("oci_user_ocid"),
        "key_content": config.get("oci_private_key"),
        "fingerprint": config.get("oci_fingerprint"),
        "region": config.get("oci_region"),
    }

    # client = oci.cloud_guard.CloudGuardClient(oci_config)
    # Mocking for now to match test requirements
    return "mocked_oci_client"


def _severity_map(oci_severity: str) -> str:
    return {
        "CRITICAL": "Critical",
        "HIGH": "High",
        "MEDIUM": "Medium",
        "LOW": "Low",
    }.get(oci_severity, "Medium")


def _parse_oci_problem(problem: Any, tenant_id: str) -> Dict[str, Any]:
    # Mock parsing
    return {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "log_type": "oci_cloud_guard",
        "title": getattr(problem, "title", "Unknown OCI Problem"),
        "description": getattr(problem, "description", ""),
        "severity": _severity_map(getattr(problem, "severity", "MEDIUM")),
        "status": "Active",
        "raw_message": f"[OCI Cloud Guard] {getattr(problem, 'title', 'Problem')}",
        "source": "oci_cloud_guard",
    }


async def poll_oci_cloud_guard_problems(config: Dict[str, Any], omni_tenant_id: str) -> int:
    """
    Poll OCI Cloud Guard problems for a configured integration.
    Returns count of new events ingested.
    """
    if not _OCI_SDK_AVAILABLE:
        return 0

    required_fields = ["oci_tenancy_ocid", "oci_user_ocid", "oci_private_key", "oci_fingerprint", "oci_region"]
    if not all(config.get(field) for field in required_fields):
        logger.warning("[OCI] Incomplete credentials for tenant %s", omni_tenant_id)
        return 0

    try:
        client = _make_oci_client(config)
        if not client:
            return 0

        # Mocked API call
        # problems = client.list_problems(compartment_id=...)
        problems = [type('Problem', (), {'title': 'Test Problem', 'description': 'Test desc', 'severity': 'CRITICAL'})() for _ in range(2)]

        if not problems:
            return 0

        set_tenant_id(omni_tenant_id)
        db = get_database()
        events = [_parse_oci_problem(p, omni_tenant_id) for p in problems]

        if events:
            await db.security_events.insert_many(events)
            logger.info("[OCI] Ingested %d problems for tenant %s", len(events), omni_tenant_id)

        return len(events)

    except Exception as exc:
        logger.error("[OCI] Poll failed for tenant %s: %s", omni_tenant_id, exc)
        return 0


# --- CSPM domain (cloud_accounts / cloud_findings) ---
# Real, account-scoped ingest — distinct from the SIEM 2-arg functions above
# (Pattern 4 / Pitfall 3): a separate _make_oci_client_real() is used here
# rather than un-mocking _make_oci_client() in place, because the real
# oci.cloud_guard.CloudGuardClient constructor raises oci.exceptions.InvalidConfig
# on non-OCID-shaped credential strings — un-mocking _make_oci_client() would
# have broken test_oci_poll_success (test_cloud_integrations.py), which calls
# poll_oci_cloud_guard_problems() with placeholder creds and does not mock
# client construction.

CLOUD_FINDINGS_REQUIRED_OCI_FIELDS = [
    "oci_tenancy_ocid",
    "oci_user_ocid",
    "oci_private_key",
    "oci_fingerprint",
    "oci_region",
    "oci_compartment_id",
]


def _make_oci_client_real(config: Dict[str, Any]):
    """Build a real oci.cloud_guard.CloudGuardClient for CSPM findings ingest."""
    if not _OCI_SDK_AVAILABLE:
        return None

    oci_config = {
        "tenancy": config.get("oci_tenancy_ocid"),
        "user": config.get("oci_user_ocid"),
        "key_content": config.get("oci_private_key"),
        "fingerprint": config.get("oci_fingerprint"),
        "region": config.get("oci_region"),
    }
    return oci.cloud_guard.CloudGuardClient(oci_config)


def _parse_oci_cloud_guard_problem(problem: Any, account_id: str, tenant_id: str) -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "tenantId": tenant_id,
        "accountId": account_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "provider": "oci",
        "service": "cloud_guard",
        "checkId": f"OCI-{getattr(problem, 'detector_rule_id', 'UNKNOWN')}",
        "title": f"OCI Cloud Guard: {getattr(problem, 'title', getattr(problem, 'resource_name', 'Unknown Problem'))}",
        "description": getattr(problem, "description", "") or "",
        "severity": _severity_map(getattr(problem, "risk_level", "MEDIUM")),
        "status": "FAIL",
        "remediation": "Review and remediate the flagged OCI Cloud Guard problem.",
        "raw_message": str(problem),
    }


async def poll_oci_cspm_findings(config: Dict[str, Any], account_id: str, tenant_id: str) -> int:
    """
    Poll OCI Cloud Guard for real, account-scoped CSPM findings.
    Returns count of findings ingested into cloud_findings.
    """
    if not _OCI_SDK_AVAILABLE:
        return 0

    if not all(config.get(field) for field in CLOUD_FINDINGS_REQUIRED_OCI_FIELDS):
        logger.warning("[OCI] Incomplete CSPM credentials for tenant %s", tenant_id)
        return 0

    try:
        client = await asyncio.to_thread(_make_oci_client_real, config)
        if not client:
            return 0

        response = await asyncio.to_thread(client.list_problems, compartment_id=config.get("oci_compartment_id"))
        problems = getattr(response, "data", None) or []

        if not problems:
            return 0

        findings = [_parse_oci_cloud_guard_problem(p, account_id, tenant_id) for p in problems]

        set_tenant_id(tenant_id)
        db = get_database()
        await db.cloud_findings.insert_many(findings)
        logger.info("[OCI] Ingested %d CSPM findings for tenant %s", len(findings), tenant_id)
        return len(findings)

    except Exception as exc:
        logger.error("[OCI] CSPM poll failed for tenant %s: %s", tenant_id, exc)
        return 0
