import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from notification_service import get_notification_service, send_notification

logger = logging.getLogger(__name__)

class ItamNotificationService:
    def __init__(self, db):
        self.db = db
        self.generic_notification_service = get_notification_service(db)

    async def send_warranty_expiry_alert(
        self,
        tenant_id: str,
        asset_id: str,
        asset_tag: str,
        warranty_status: str,
        warranty_expires_at: str,
        recipients: List[str]
    ) -> Dict[str, Any]:
        title = "ITAM Asset Warranty Alert"
        message = (
            f"Asset '{asset_tag}' (ID: {asset_id}) warranty is {warranty_status}. "
            f"Expires on {warranty_expires_at}."
        )
        metadata = {
            "asset_id": asset_id,
            "asset_tag": asset_tag,
            "warranty_status": warranty_status,
            "warranty_expires_at": warranty_expires_at,
            "event_type": "itam.warranty_expiring"
        }

        # Send via generic in-app notification service
        try:
            await self.generic_notification_service.send_alert(
                title=title,
                message=message,
                severity="warning",
                recipients=recipients,
                tenant_id=tenant_id,
                channels=[], # In-app only
                metadata=metadata
            )
        except Exception as e:
            logger.error(f"Failed to send in-app warranty alert for asset {asset_id}: {e}")

        # Send via rule-routed notification service (e.g., Slack, email via rules)
        try:
            # send_notification requires a _db attribute, so pass the raw db wrapped
            raw_handle = self.db._db if hasattr(self.db, "_db") else self.db
            await send_notification(
                _RawDbForNotificationRules(raw_handle),
                tenant_id,
                "itam.warranty_expiring",
                {
                    "message": message,
                    "severity": "warning",
                    **metadata
                }
            )
        except Exception as e:
            logger.error(f"Failed to send rule-routed warranty alert for asset {asset_id}: {e}")

        return {"status": "alerts sent"}


class _RawDbForNotificationRules:
    """Minimal adapter exposing the single `_db` attribute
    notification_service.send_notification reads on its first line."""
    __slots__ = ("_db",)
    def __init__(self, db):
        self._db = db