"""The in-app notice to the person who raised a ticket on the portal (D-12, D-33).

The notice is stored through ``send_alert`` with no channels, so nothing is emailed, texted or posted
to a chat tool. It is tagged ``metadata.recipient`` (the reporter, lowercase): the notification list
shows it to that person only, and the tenant-wide live push carries its title alone. The text is
generic on purpose: the ticket number, never a preview of any ticket text (T-85-06).
"""
import logging
from typing import Any, Dict, Optional

from autonomous_ops.scope import raw
from service_desk import messages

logger = logging.getLogger(__name__)


async def requester_notice(db, ticket: Dict[str, Any], *, event: str, title: Optional[str] = None,
                           message: Optional[str] = None) -> bool:
    """Store one notice for the reporter of ``ticket``. True when it was stored. Only a portal requester
    gets one (a tray requester reads the tray window; an automated ticket has no requester). Never raises."""
    try:
        channel = ticket.get("requester_channel")
        reporter = ticket.get("reporter")
        tenant = ticket.get("tenantId")
        if not (isinstance(channel, dict) and channel.get("portal") is True):
            return False
        if not (isinstance(reporter, str) and reporter.strip() and isinstance(tenant, str) and tenant):
            return False
        text = messages.NOTICE_TITLE.format(number=ticket.get("ticket_number") or "")
        from notification_service import get_notification_service
        await get_notification_service(raw(db)).send_alert(
            title or text, message or text, "info", recipients=[], tenant_id=tenant, channels=[],
            metadata={"recipient": reporter.strip().lower(), "ticket_id": ticket.get("id"), "event": event})
        return True
    except Exception as exc:
        logger.warning("service_desk: requester notice not stored: %s", exc)
        return False
