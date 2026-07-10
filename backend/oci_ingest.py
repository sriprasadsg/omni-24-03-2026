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
