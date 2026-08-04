import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from ocsf_endpoints import _to_epoch, severity_map
from webhook_service import WebhookService

logger = logging.getLogger(__name__)

# Re-use existing WebhookService instance for consistent behavior (SSRF/HMAC)
_webhook_service = WebhookService()

async def push_ocsf_event(event_type: str, source_doc: Dict[str, Any]):
    """
    Builds an OCSF Detection Finding payload and dispatches it via a fire-and-forget webhook.
    Errors during OCSF construction or dispatch are logged but swallowed to avoid blocking
    the calling pipeline.
    """
    try:
        # Map source_doc fields to OCSF Detection Finding (class_uid=2004)
        # Reuses _to_epoch and severity_map from ocsf_endpoints.py
        # Fallbacks for missing fields to ensure valid OCSF structure
        event_id = source_doc.get("id", f"ocsf-event-{asyncio.current_task().get_name()}-{datetime.now().timestamp()}")
        title = source_doc.get("title", "Unknown Detection Finding")
        severity = source_doc.get("severity", "medium").lower()
        sev_id = severity_map.get(severity, 3)
        timestamp = source_doc.get("createdAt") or source_doc.get("timestamp") or datetime.now(timezone.utc).isoformat()

        ocsf_payload = {
            "class_uid": 2004,
            "category_uid": 2,
            "type_uid": 200401,
            "severity_id": sev_id,
            "severity": severity,
            "finding": {"uid": event_id, "title": title},
            "time": _to_epoch(timestamp),
            "metadata": {"version": "1.0.0", "product": {"name": "OmniAgent Platform"}},
            "resources": [], # Populate as needed, not strictly required by plan
            "data": source_doc, # Include original doc for full context
        }

        # Fire-and-forget dispatch
        asyncio.create_task(_webhook_service.trigger_webhook(event_type, ocsf_payload))
        logger.info("Dispatched OCSF event '%s' (type: %s) to webhooks.", event_id, event_type)

    except Exception as e:
        logger.warning("Failed to push OCSF event for type '%s': %s", event_type, e)
