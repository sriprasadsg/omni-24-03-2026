"""Outbound webhook dispatch for ticket events."""
import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx
from fastapi import HTTPException
from database import mongodb
from webhook_security import is_safe_webhook_url

logger = logging.getLogger(__name__)

SUPPORTED_EVENTS = {
    "ticket.created", "ticket.updated", "ticket.status_changed",
    "ticket.commented", "ticket.escalated", "ticket.resolved",
    "ticket.csat_submitted", "ticket.merged",
}


async def get_webhooks(tenant_id: str) -> List[Dict]:
    return await mongodb.db.ticket_webhooks.find(
        {"tenant_id": tenant_id, "active": True}, {"_id": 0}
    ).to_list(length=100)


async def register_webhook(
    tenant_id: str, url: str, events: List[str], secret: str = ""
) -> Dict:
    # SSRF: this subsystem had no URL validation at all (2026-08-25 audit) —
    # a tenant admin (manage:settings) could point a ticket webhook at any
    # internal/metadata address and it would be dispatched on every ticket
    # lifecycle event.
    if not is_safe_webhook_url(url):
        raise HTTPException(status_code=400, detail="Invalid or disallowed webhook URL")
    hook = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "url": url,
        "events": [e for e in events if e in SUPPORTED_EVENTS],
        "secret": secret,
        "active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_triggered_at": None,
        "failure_count": 0,
    }
    await mongodb.db.ticket_webhooks.insert_one(hook)
    hook.pop("_id", None)
    return hook


async def delete_webhook(tenant_id: str, webhook_id: str) -> bool:
    result = await mongodb.db.ticket_webhooks.delete_one(
        {"id": webhook_id, "tenant_id": tenant_id}
    )
    return result.deleted_count > 0


async def dispatch_event(
    tenant_id: str, event: str, payload: Dict[str, Any]
) -> None:
    """Fire-and-forget: dispatch event to all matching webhooks for the tenant."""
    webhooks = await mongodb.db.ticket_webhooks.find(
        {"tenant_id": tenant_id, "active": True, "events": event}, {"_id": 0}
    ).to_list(length=50)

    for hook in webhooks:
        try:
            # SSRF: re-validate immediately before dispatch — narrows (does
            # not eliminate) the DNS-rebinding window, and this is also the
            # only check at all for any hook registered before this fix.
            if not is_safe_webhook_url(hook.get("url", "")):
                logger.warning(
                    "Skipping ticket webhook %s: URL fails SSRF validation", hook.get("id")
                )
                continue
            body = json.dumps({
                "event": event,
                "payload": payload,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            headers: Dict[str, str] = {
                "Content-Type": "application/json",
                "X-Webhook-Event": event,
            }
            if hook.get("secret"):
                sig = hmac.new(
                    hook["secret"].encode(), body.encode(), hashlib.sha256
                ).hexdigest()
                headers["X-Webhook-Signature"] = f"sha256={sig}"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(hook["url"], content=body, headers=headers)
                await mongodb.db.ticket_webhooks.update_one(
                    {"id": hook["id"]},
                    {"$set": {
                        "last_triggered_at": datetime.now(timezone.utc).isoformat(),
                        "last_status_code": resp.status_code,
                    }},
                )
        except Exception as exc:
            logger.warning("Webhook %s failed: %s", hook.get("url"), exc)
            await mongodb.db.ticket_webhooks.update_one(
                {"id": hook["id"]}, {"$inc": {"failure_count": 1}}
            )
