"""
Okta System Log SIEM Ingest
Polls the Okta /api/v1/logs endpoint for each configured tenant integration
and ingests events into security_events collection.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from database import get_database

logger = logging.getLogger(__name__)

try:
    import aiohttp
    _AIOHTTP_AVAILABLE = True
except ImportError:
    _AIOHTTP_AVAILABLE = False
    logger.warning("[Okta] aiohttp not installed — Okta log ingest disabled")


def _parse_okta_event(event: Dict[str, Any], tenant_id: str) -> Dict[str, Any]:
    outcome = event.get("outcome", {}) or {}
    actor = event.get("actor", {}) or {}
    client = event.get("client", {}) or {}
    return {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "timestamp": event.get("published", datetime.now(timezone.utc).isoformat()),
        "log_type": "okta_system",
        "eventType": event.get("eventType", ""),
        "displayMessage": event.get("displayMessage", ""),
        "severity": event.get("severity", "INFO"),
        "outcome_result": outcome.get("result", ""),
        "outcome_reason": outcome.get("reason", ""),
        "actor_id": actor.get("id", ""),
        "actor_type": actor.get("type", ""),
        "actor_login": actor.get("alternateId", ""),
        "actor_name": actor.get("displayName", ""),
        "client_ip": client.get("ipAddress", ""),
        "client_device": client.get("device", ""),
        "client_os": (client.get("userAgent") or {}).get("os", ""),
        "client_browser": (client.get("userAgent") or {}).get("browser", ""),
        "raw_message": f"{event.get('eventType', '')} {outcome.get('result', '')}",
    }


async def fetch_okta_logs(
    tenant_id: str,
    domain: str,
    api_token: str,
    since: datetime,
) -> int:
    """
    Fetch Okta system logs since `since` timestamp.
    Returns count of events ingested.
    """
    if not _AIOHTTP_AVAILABLE:
        return 0
    if not domain or api_token in ("", "fake_token", None):
        logger.debug("[Okta] No valid credentials for tenant %s — skipping", tenant_id)
        return 0

    db = get_database()
    ingested = 0
    since_str = since.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    url = f"https://{domain}/api/v1/logs"
    headers = {"Authorization": f"SSWS {api_token}", "Accept": "application/json"}
    params = {"since": since_str, "limit": 1000, "sortOrder": "ASCENDING"}

    try:
        async with aiohttp.ClientSession() as session:
            while url:
                async with session.get(url, headers=headers, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 401:
                        logger.error("[Okta] Invalid API token for tenant %s", tenant_id)
                        break
                    if resp.status == 429:
                        await asyncio.sleep(60)
                        continue
                    if resp.status != 200:
                        logger.error("[Okta] HTTP %d for tenant %s", resp.status, tenant_id)
                        break

                    events = await resp.json()
                    if not events:
                        break

                    docs = [_parse_okta_event(e, tenant_id) for e in events]
                    await db.security_events.insert_many(docs)
                    ingested += len(docs)

                    # Follow next-page link header
                    link_header = resp.headers.get("Link", "")
                    next_url = None
                    for part in link_header.split(","):
                        if 'rel="next"' in part:
                            next_url = part.split(";")[0].strip().strip("<>")
                    url = next_url
                    params = {}  # params already baked into next_url

    except Exception as exc:
        logger.error("[Okta] Fetch error for tenant %s: %s", tenant_id, exc)

    if ingested:
        logger.info("[Okta] Ingested %d events for tenant %s", ingested, tenant_id)
    return ingested


async def start_okta_polling():
    """Poll every 60 seconds for each configured Okta integration."""
    from tenant_context import set_tenant_id
    while True:
        try:
            set_tenant_id("platform-admin")
            db = get_database()
            configs = await db.siem_configs.find({"provider": "okta", "enabled": True}).to_list(length=100)
            for config in configs:
                await fetch_okta_logs(
                    tenant_id=config.get("tenant_id", "default"),
                    domain=config.get("domain", ""),
                    api_token=config.get("api_token", ""),
                    since=datetime.now(timezone.utc) - timedelta(minutes=1),
                )
        except Exception as exc:
            logger.error("[Okta] Polling loop error: %s", exc)

        await asyncio.sleep(60)
