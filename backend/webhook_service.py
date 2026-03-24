import httpx
from datetime import datetime
from database import get_database

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
            
        print(f"[WebhookService] Triggering {len(webhooks)} webhooks for event: {event_type}")
        
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
        headers = hook.get('headers', {})
        
        # Default headers
        headers['Content-Type'] = 'application/json'
        headers['User-Agent'] = 'Omni-Agent-Platform/1.0'
        
        try:
            response = await client.post(url, json=payload, headers=headers, timeout=10.0)
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
                    {"$set": update_doc, "$set": {"failureCount": 0}}
                )
                
        except Exception as e:
            print(f"[WebhookService] Failed to send to {url}: {e}")
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
