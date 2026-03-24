import asyncio
from typing import Dict, Any, List
from email_service import email_service
from webhook_service import WebhookService
from database import get_database

class NotificationManager:
    def __init__(self):
        self.webhook_service = WebhookService()

    async def send_notification(self, event_type: str, payload: Dict[str, Any], tenant_id: str):
        """
        Dispatch notification to enabled channels for the tenant.
        This method is async and should be called with await or added to background tasks.
        """
        print(f"[NotificationManager] Dispatching {event_type} for tenant {tenant_id}")
        
        # 1. Webhooks (Fire and Forget)
        # WebhookService handles finding active webhooks for the event
        # We wrap it in create_task to ensure it doesn't block if called with await
        asyncio.create_task(self.webhook_service.trigger_webhook(event_type, payload))
        
        # 2. Email
        # Check if email is configured and relevant for this event
        if event_type in ["agent.offline", "security.alert", "compliance.violation"]:
            # We also wrap email dispatch in create_task
            asyncio.create_task(self._dispatch_email(event_type, payload, tenant_id))

    async def _dispatch_email(self, event_type: str, payload: Dict[str, Any], tenant_id: str):
        try:
            db = get_database()
            if not db: return

            # Get Tenant Settings for SMTP
            smtp_settings = await db.settings.find_one({"type": "smtp", "tenantId": tenant_id})
            if not smtp_settings:
                # Try global fallback (platform-admin)
                smtp_settings = await db.settings.find_one({"type": "smtp", "tenantId": "platform-admin"})
                
            if not smtp_settings:
                print("[NotificationManager] No SMTP settings found. Skipping email.")
                return

            # Get Recipients (Admins of the tenant)
            # Find users with role 'Admin' or 'Super Admin' in this tenant
            # In a real app, we'd check permissions or notification preferences
            users = await db.users.find({"tenantId": tenant_id}).to_list(length=100)
            recipients = [u['email'] for u in users if u.get('email')]
            
            if not recipients:
                print("[NotificationManager] No recipients found.")
                return

            # Format Email
            subject = f"Notification: {event_type}"
            body = f"Event: {event_type}\nData: {payload}"
            
            if event_type == "agent.offline":
                subject = f"⚠️ Agent Offline Alert ({payload.get('count')} agents)"
                body = f"Warning: {payload.get('count')} agents have gone offline as of {payload.get('timestamp')}."
            elif event_type == "security.alert":
                subject = f"🚨 Security Alert: {payload.get('title')}"
                body = f"Severity: {payload.get('severity')}\nDescription: {payload.get('description')}"

            # Send Email (using run_in_executor to avoid blocking main loop)
            loop = asyncio.get_running_loop()
            
            # Send to each recipient (or use BCC in real impl)
            for recipient in recipients:
                await loop.run_in_executor(
                    None, 
                    lambda: email_service.send_email(
                        smtp_config=smtp_settings['config'],
                        to_email=recipient,
                        subject=subject,
                        body_text=body
                    )
                )
                print(f"[NotificationManager] Email sent to {recipient}")
                
        except Exception as e:
            print(f"[NotificationManager] Error dispatching email: {e}")

notification_manager = NotificationManager()
