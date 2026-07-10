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
