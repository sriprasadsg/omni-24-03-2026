"""
Notification triggers for internal ticket events.
Called non-fatally from tickets_service after state changes.
"""
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class _DbAdapter:
    """Expose raw mongo handle the module-level send_notification reads."""
    __slots__ = ("_db",)
    def __init__(self, db):
        self._db = db._db if hasattr(db, "_db") else db


async def _send(title: str, message: str, severity: str, recipients: list, metadata: dict, tenant_id: str = "") -> None:
    try:
        from database import get_database
        from notification_service import get_notification_service, send_notification as _route
        db = get_database()
        # In-app notification (writes db.notifications, feeds bell + popup)
        await get_notification_service(db).send_alert(
            title=title,
            message=message,
            severity=severity,
            recipients=recipients,
            tenant_id=tenant_id,
            channels=[],  # in-app only; rule routing handled below
            metadata=metadata,
        )
        # Rule-routed external channels (email/slack/webhook) bound to the event
        if tenant_id:
            await _route(_DbAdapter(db), tenant_id, metadata.get("event", ""), {
                "message": message, "severity": severity,
            })
    except Exception as exc:
        logger.debug("Ticket notification failed (non-fatal): %s", exc)


async def notify_ticket_created(ticket: Dict[str, Any]) -> None:
    recipients = _recipients(ticket)
    if not recipients:
        return
    await _send(
        title=f"[{ticket.get('ticket_number')}] New Ticket: {ticket.get('title', '')}",
        message=(
            f"A new {ticket.get('priority', 'medium')} priority "
            f"{ticket.get('type', 'task')} ticket has been created.\n\n"
            f"Reporter: {ticket.get('reporter', 'unknown')}\n"
            f"Due: {ticket.get('due_date', 'N/A')}"
        ),
        severity="info",
        recipients=recipients,
        metadata={"ticket_id": ticket.get("id"), "event": "ticket_created"},
        tenant_id=ticket.get("tenantId", ""),
    )


async def notify_status_changed(ticket: Dict[str, Any], old_status: str, actor: str) -> None:
    recipients = _recipients(ticket)
    if not recipients:
        return
    new_status = ticket.get("status", "")
    await _send(
        title=f"[{ticket.get('ticket_number')}] Status changed: {old_status} → {new_status}",
        message=(
            f"Ticket '{ticket.get('title', '')}' status was changed "
            f"from {old_status} to {new_status} by {actor}."
        ),
        severity="info",
        recipients=recipients,
        metadata={"ticket_id": ticket.get("id"), "event": "ticket_status_changed"},
        tenant_id=ticket.get("tenantId", ""),
    )


async def notify_assigned(ticket: Dict[str, Any], new_assignee: str, actor: str) -> None:
    recipients = [new_assignee] if "@" in new_assignee else []
    if not recipients:
        return
    await _send(
        title=f"[{ticket.get('ticket_number')}] Assigned to you",
        message=(
            f"Ticket '{ticket.get('title', '')}' has been assigned to you by {actor}.\n"
            f"Priority: {ticket.get('priority', 'medium')}\n"
            f"Due: {ticket.get('due_date', 'N/A')}"
        ),
        severity="warning" if ticket.get("priority") in ("critical", "high") else "info",
        recipients=recipients,
        metadata={"ticket_id": ticket.get("id"), "event": "ticket_assigned"},
        tenant_id=ticket.get("tenantId", ""),
    )


async def notify_sla_breached(ticket: Dict[str, Any]) -> None:
    recipients = _recipients(ticket)
    if not recipients:
        return
    await _send(
        title=f"[{ticket.get('ticket_number')}] SLA Breached — {ticket.get('title', '')}",
        message=(
            f"Ticket '{ticket.get('title', '')}' has breached its SLA.\n"
            f"Priority: {ticket.get('priority', 'medium')}\n"
            f"Assignee: {ticket.get('assignee', 'unassigned')}\n"
            f"Due was: {ticket.get('due_date', 'N/A')}"
        ),
        severity="critical",
        recipients=recipients,
        metadata={"ticket_id": ticket.get("id"), "event": "ticket_sla_breached"},
        tenant_id=ticket.get("tenantId", ""),
    )


async def notify_escalated(ticket: Dict[str, Any], actor: str, reason: str) -> None:
    recipients = _recipients(ticket)
    if not recipients:
        return
    await _send(
        title=f"[{ticket.get('ticket_number')}] Escalated (Level {ticket.get('escalation_level', 1)})",
        message=(
            f"Ticket '{ticket.get('title', '')}' was escalated by {actor}.\n"
            f"Reason: {reason or 'Not specified'}\n"
            f"New priority: {ticket.get('priority', 'medium')}"
        ),
        severity="critical",
        recipients=recipients,
        metadata={"ticket_id": ticket.get("id"), "event": "ticket_escalated"},
        tenant_id=ticket.get("tenantId", ""),
    )


async def notify_comment_added(ticket: Dict[str, Any], author: str, preview: str, visibility: str = "staff") -> None:
    """A comment notice. Staff-only text never leaves the staff: that notice has no preview, is not addressed
    to the reporter, is tagged for ticket staff and names the reporter as excluded, so the notifications feed
    does not serve it to them and the tenant socket does not push it (WR-201). A requester-visible comment keeps
    its preview and is tagged with the one person it is for, so the notifications reader serves it to that
    person only (D-33)."""
    reporter = str(ticket.get("reporter") or "").strip().casefold()
    title = f"[{ticket.get('ticket_number')}] New comment by {author}"
    if visibility == "requester":
        if not reporter or reporter == str(author or "").strip().casefold():
            return                      # no one to tell, and an untagged preview would reach the whole feed
        recipients = [r for r in _recipients(ticket) if r != author]
        message = f"'{preview[:100]}...' — on ticket '{ticket.get('title', '')}'"
        metadata = {"ticket_id": ticket.get("id"), "event": "ticket_comment_added", "recipient": reporter}
    else:
        recipients = [r for r in _recipients(ticket) if r != author and r.casefold() != reporter]
        message = f"New staff comment on ticket '{ticket.get('title', '')}'"
        metadata = {"ticket_id": ticket.get("id"), "event": "ticket_comment_added", "audience": "ticket_staff"}
        if reporter:
            metadata["excludeRecipients"] = [reporter]
    if not recipients:
        return
    await _send(
        title=title,
        message=message,
        severity="info",
        recipients=recipients,
        metadata=metadata,
        tenant_id=ticket.get("tenantId", ""),
    )


def _recipients(ticket: Dict[str, Any]) -> list:
    """Collect email-like strings from reporter, assignee, and watchers."""
    candidates = [
        ticket.get("reporter", ""),
        ticket.get("assignee", ""),
        *ticket.get("watchers", []),
    ]
    return list({r for r in candidates if r and "@" in r})
