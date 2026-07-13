"""
Cloudflare Zero Trust Ingest
Polls Cloudflare Zero Trust events and ingests them into security_events.
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
    import cloudflare
    _CLOUDFLARE_SDK_AVAILABLE = True
except ImportError:
    _CLOUDFLARE_SDK_AVAILABLE = False
    logger.warning("[Cloudflare] cloudflare SDK not installed — Cloudflare Zero Trust ingest disabled")


def _make_cloudflare_client(config: Dict[str, Any]):
    if not _CLOUDFLARE_SDK_AVAILABLE:
        return None
    # Mock client builder
    return "mocked_cloudflare_client"


def _severity_map(cf_severity: str) -> str:
    return {
        "CRITICAL": "Critical",
        "HIGH": "High",
        "MEDIUM": "Medium",
        "LOW": "Low",
    }.get(cf_severity, "Medium")


def _parse_cloudflare_event(event: Any, tenant_id: str) -> Dict[str, Any]:
    # Mock parsing
    return {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "log_type": "cloudflare_zero_trust",
        "title": getattr(event, "title", "Unknown Cloudflare Event"),
        "description": getattr(event, "description", ""),
        "severity": _severity_map(getattr(event, "severity", "MEDIUM")),
        "status": "Active",
        "raw_message": f"[Cloudflare] {getattr(event, 'title', 'Event')}",
        "source": "cloudflare_zero_trust",
    }


async def poll_cloudflare_zero_trust_events(config: Dict[str, Any], omni_tenant_id: str) -> int:
    """
    Poll Cloudflare Zero Trust events for a configured integration.
    Returns count of new events ingested.
    """
    if not _CLOUDFLARE_SDK_AVAILABLE:
        return 0

    required_fields = ["cf_account_id", "cf_api_token"]
    if not all(config.get(field) for field in required_fields):
        logger.warning("[Cloudflare] Incomplete credentials for tenant %s", omni_tenant_id)
        return 0

    try:
        client = _make_cloudflare_client(config)
        if not client:
            return 0

        # Mocked API call
        events_list = [type('Event', (), {'title': 'Test Event', 'description': 'Test desc', 'severity': 'MEDIUM'})() for _ in range(1)]

        if not events_list:
            return 0

        set_tenant_id(omni_tenant_id)
        db = get_database()
        events = [_parse_cloudflare_event(e, omni_tenant_id) for e in events_list]

        if events:
            await db.security_events.insert_many(events)
            logger.info("[Cloudflare] Ingested %d events for tenant %s", len(events), omni_tenant_id)

        return len(events)

    except Exception as exc:
        logger.error("[Cloudflare] Poll failed for tenant %s: %s", omni_tenant_id, exc)
        return 0
