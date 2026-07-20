"""
Alibaba Cloud Security Center (SAS) Ingest
Polls Alibaba SAS alerts and ingests them into security_events.
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
    from aliyunsdkcore.client import AcsClient
    _ALIBABA_SDK_AVAILABLE = True
except ImportError:
    _ALIBABA_SDK_AVAILABLE = False
    logger.warning("[Alibaba] aliyun-python-sdk-core-v3 not installed — Alibaba SAS ingest disabled")

# V2 typed SDK (CSPM domain) — separate availability flag from the legacy V1
# AcsClient import above so both paths can coexist; the new CSPM ingest
# function below must never use AcsClient/CommonRequest (RESEARCH Standard
# Stack / Don't Hand-Roll).
try:
    from alibabacloud_tea_openapi import models as alibaba_openapi_models
    from alibabacloud_sas20181203.client import Client as AlibabaSasClient
    from alibabacloud_sas20181203 import models as alibaba_sas_models
    _ALIBABA_V2_SDK_AVAILABLE = True
except ImportError:
    _ALIBABA_V2_SDK_AVAILABLE = False
    logger.warning("[Alibaba] alibabacloud_* V2 SDK not installed — Alibaba CSPM ingest disabled")


def _make_alibaba_client(config: Dict[str, Any]):
    if not _ALIBABA_SDK_AVAILABLE:
        return None
    # Mock client builder
    return "mocked_alibaba_client"


def _severity_map(ali_severity: int) -> str:
    # SAS severity: 1 (Urgent), 2 (High), 3 (Medium), 4 (Low)
    return {
        1: "Critical",
        2: "High",
        3: "Medium",
        4: "Low",
    }.get(ali_severity, "Medium")


def _parse_alibaba_alert(alert: Any, tenant_id: str) -> Dict[str, Any]:
    # Mock parsing
    return {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "log_type": "alibaba_sas",
        "title": getattr(alert, "title", "Unknown Alibaba Alert"),
        "description": getattr(alert, "description", ""),
        "severity": _severity_map(getattr(alert, "severity", 3)),
        "status": "Active",
        "raw_message": f"[Alibaba SAS] {getattr(alert, 'title', 'Alert')}",
        "source": "alibaba_sas",
    }


async def poll_alibaba_sas_alerts(config: Dict[str, Any], omni_tenant_id: str) -> int:
    """
    Poll Alibaba SAS alerts for a configured integration.
    Returns count of new events ingested.
    """
    if not _ALIBABA_SDK_AVAILABLE:
        return 0

    required_fields = ["access_key_id", "access_key_secret", "region_id"]
    if not all(config.get(field) for field in required_fields):
        logger.warning("[Alibaba] Incomplete credentials for tenant %s", omni_tenant_id)
        return 0

    try:
        client = _make_alibaba_client(config)
        if not client:
            return 0

        # Mocked API call
        alerts = [type('Alert', (), {'title': 'Test Alert', 'description': 'Test desc', 'severity': 1})() for _ in range(3)]

        if not alerts:
            return 0

        set_tenant_id(omni_tenant_id)
        db = get_database()
        events = [_parse_alibaba_alert(a, omni_tenant_id) for a in alerts]

        if events:
            await db.security_events.insert_many(events)
            logger.info("[Alibaba] Ingested %d alerts for tenant %s", len(events), omni_tenant_id)

        return len(events)

    except Exception as exc:
        logger.error("[Alibaba] Poll failed for tenant %s: %s", omni_tenant_id, exc)
        return 0


# --- CSPM domain (cloud_accounts / cloud_findings) — V2 typed SDK ---
# Real, account-scoped ingest — distinct from the SIEM 2-arg function above
# (Pattern 4 / Pitfall 3). Uses the V2 alibabacloud_sas20181203 typed client,
# never aliyunsdkcore.client.AcsClient/CommonRequest.

_ALIBABA_V2_REQUIRED_FIELDS = ["access_key_id", "access_key_secret", "region_id"]

_ALIBABA_V2_SEVERITY_MAP = {
    "serious": "Critical",
    "critical": "Critical",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
}

# Alibaba SAS ListCheckResult "status" values that represent a compliant
# (passing) baseline check — anything else is treated as a FAIL finding.
_ALIBABA_CSPM_PASS_STATUSES = {"pass", "passed", "ok", "normal"}


def _make_alibaba_v2_client(config: Dict[str, Any]):
    """Build a real alibabacloud_sas20181203 V2 typed client for CSPM findings ingest."""
    if not _ALIBABA_V2_SDK_AVAILABLE:
        return None

    openapi_config = alibaba_openapi_models.Config(
        access_key_id=config.get("access_key_id"),
        access_key_secret=config.get("access_key_secret"),
        region_id=config.get("region_id"),
    )
    return AlibabaSasClient(openapi_config)


def _severity_map_v2(risk_level: Any) -> str:
    return _ALIBABA_V2_SEVERITY_MAP.get(str(risk_level).lower(), "Medium")


def _parse_alibaba_check(check: Any, account_id: str, tenant_id: str) -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "tenantId": tenant_id,
        "accountId": account_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "provider": "alibaba",
        "service": "security_center",
        "checkId": f"ALI-{getattr(check, 'check_id', 'UNKNOWN')}",
        "title": f"Alibaba Security Center: {getattr(check, 'check_show_name', 'Unknown Check')}",
        "description": getattr(check, "status_message", "") or "",
        "severity": _severity_map_v2(getattr(check, "risk_level", "medium")),
        "status": "FAIL",
        "remediation": "Review and remediate the flagged Alibaba Security Center baseline check.",
        "raw_message": str(check),
    }


async def poll_alibaba_cspm_findings(config: Dict[str, Any], account_id: str, tenant_id: str) -> int:
    """
    Poll Alibaba Cloud Security Center (SAS) via the V2 typed SDK for real,
    account-scoped CSPM findings. Returns count ingested into cloud_findings.
    """
    if not _ALIBABA_V2_SDK_AVAILABLE:
        return 0

    if not all(config.get(field) for field in _ALIBABA_V2_REQUIRED_FIELDS):
        logger.warning("[Alibaba] Incomplete CSPM credentials for tenant %s", tenant_id)
        return 0

    try:
        client = await asyncio.to_thread(_make_alibaba_v2_client, config)
        if not client:
            return 0

        request = alibaba_sas_models.ListCheckResultRequest(current_page=1, page_size=50)
        response = await asyncio.to_thread(client.list_check_result, request)
        checks = getattr(getattr(response, "body", None), "checks", None) or []

        failing = [
            c for c in checks
            if str(getattr(c, "status", "")).lower() not in _ALIBABA_CSPM_PASS_STATUSES
        ]

        if not failing:
            return 0

        findings = [_parse_alibaba_check(c, account_id, tenant_id) for c in failing]

        set_tenant_id(tenant_id)
        db = get_database()
        await db.cloud_findings.insert_many(findings)
        logger.info("[Alibaba] Ingested %d CSPM findings for tenant %s", len(findings), tenant_id)
        return len(findings)

    except Exception as exc:
        logger.error("[Alibaba] CSPM poll failed for tenant %s: %s", tenant_id, exc)
        return 0
