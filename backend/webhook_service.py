import hashlib
import hmac
import ipaddress
import json
import logging
import re
import httpx
from datetime import datetime
from database import get_database

logger = logging.getLogger(__name__)

# Private / link-local / loopback CIDR ranges that must never be webhook targets
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),   # link-local / cloud metadata
    ipaddress.ip_network("100.64.0.0/10"),    # carrier-grade NAT
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),          # unique local IPv6
    ipaddress.ip_network("fe80::/10"),         # link-local IPv6
]

_LOCALHOST_RE = re.compile(r'^(localhost|.*\.local)$', re.IGNORECASE)


def _is_safe_webhook_url(url: str) -> bool:
    """Return True only if url is a public http/https target, not a private/internal address."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = parsed.hostname or ""
        if not host:
            return False
        if _LOCALHOST_RE.match(host):
            return False
        # Try to parse host as IP; if it resolves to a blocked range, reject
        try:
            addr = ipaddress.ip_address(host)
            for net in _BLOCKED_NETWORKS:
                if addr in net:
                    return False
        except ValueError:
            pass  # hostname, not IP — DNS resolution happens at request time; block obvious patterns
        return True
    except Exception as e:
        logger.debug("Webhook URL private-IP check failed: %s", e)
        return False


class WebhookService:
    async def trigger_webhook(self, event_type: str, payload: dict):
        """
        Triggers all webhooks configured for a specific event type.
        """
        db = get_database()
        
        # Find active webhooks that subscribe to this event type
        # efficient query: status is Active AND events contains event_type
        cursor = db.webhooks.find({
            "status": "Active",
            "events": event_type
        })
        
        webhooks = await cursor.to_list(length=100)
        
        if not webhooks:
            return
            
        logger.info("[WebhookService] Triggering %d webhooks for event: %s", len(webhooks), event_type)
        
        # Prepare the standard payload wrapper
        webhook_payload = {
            "event": event_type,
            "timestamp": datetime.now().isoformat(),
            "data": payload
        }
        
        async with httpx.AsyncClient() as client:
            for hook in webhooks:
                await self._send_single_webhook(client, hook, webhook_payload, db)

    async def _send_single_webhook(self, client, hook, payload, db):
        url = hook.get('url')
        if not url or not _is_safe_webhook_url(url):
            logger.warning("[WebhookService] Blocked delivery to unsafe URL: %s", url)
            return
        headers = hook.get('headers', {})
        
        # Default headers
        headers['Content-Type'] = 'application/json'
        headers['User-Agent'] = 'Omni-Agent-Platform/1.0'

        # Sign the exact bytes sent on the wire (never httpx json= — it re-serializes
        # independently, so the receiver's HMAC over the raw body would not match)
        body = json.dumps(payload)
        if hook.get('secret'):
            sig = hmac.new(hook['secret'].encode(), body.encode(), hashlib.sha256).hexdigest()
            headers['X-Webhook-Signature'] = f"sha256={sig}"

        try:
            response = await client.post(url, content=body, headers=headers, timeout=10.0)
            success = response.status_code >= 200 and response.status_code < 300

            # Update webhook status
            update_doc = {
                "lastResult": {
                    "timestamp": datetime.now().isoformat(),
                    "status": response.status_code,
                    "success": success
                }
            }

            if not success:
                # Increment failure count
                await db.webhooks.update_one(
                    {"id": hook['id']},
                    {"$set": update_doc, "$inc": {"failureCount": 1}}
                )
            else:
                # Reset failure count on success
                await db.webhooks.update_one(
                    {"id": hook['id']},
                    {"$set": {**update_doc, "failureCount": 0}}
                )

            # Record the delivery so GET /api/webhooks/{id}/deliveries (and the
            # Zapier trigger's performList) sees real dispatches, not just pings
            try:
                await db.webhook_deliveries.insert_one({
                    "webhook_id": hook["id"],
                    "event": payload.get("event"),
                    "payload": payload,
                    "success": success,
                    "status_code": response.status_code,
                    "timestamp": datetime.now().isoformat(),
                })
            except Exception as e:
                logger.debug("Failed to record webhook delivery: %s", e)

        except Exception as e:
            logger.warning("[WebhookService] Failed to send to %s: %s", url, e)
            # Update with error
            await db.webhooks.update_one(
                {"id": hook['id']},
                {
                    "$set": {
                        "lastResult": {
                            "timestamp": datetime.now().isoformat(),
                            "error": str(e),
                            "success": False
                        }
                    },
                    "$inc": {"failureCount": 1}
                }
            )
