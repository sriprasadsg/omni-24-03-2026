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


async def poll_alibaba_sas_alerts(config: Dict[str, Any], omni_tenant_id: str) -> int:
    """
    Poll Alibaba SAS alerts for a configured integration.
    Returns count of new events ingested.

    No real SIEM-domain polling is wired here (32-REVIEW.md CR-01): this
    used to fabricate hardcoded "Test Alert" events and write them into
    security_events unlabeled, corrupting the SIEM with invented findings.
    poll_alibaba_cspm_findings() below is the real, tested Security Center
    integration (CSPM domain) — this SIEM-domain function fails safe
    (0 events) until it gets a real implementation.
    """
    if not _ALIBABA_SDK_AVAILABLE:
        return 0

    required_fields = ["access_key_id", "access_key_secret", "region_id"]
    if not all(config.get(field) for field in required_fields):
        logger.warning("[Alibaba] Incomplete credentials for tenant %s", omni_tenant_id)
        return 0

    logger.warning("[Alibaba] SIEM poll for tenant %s: not implemented, no findings ingested", omni_tenant_id)
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
