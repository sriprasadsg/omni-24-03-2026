"""
Notification triggers for internal ticket events.
Called non-fatally from tickets_service after state changes.
"""
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


async def _send(title: str, message: str, severity: str, recipients: list, metadata: dict) -> None:
    try:
        from notification_service import notification_service
        await notification_service.send_alert(
            title=title,
            message=message,
            severity=severity,
            recipients=recipients,
            channels=["email"],
            metadata=metadata,
        )
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
        metadata={"ticket_id": ticket.get("id"), "event": "created"},
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
        metadata={"ticket_id": ticket.get("id"), "event": "status_changed"},
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
        metadata={"ticket_id": ticket.get("id"), "event": "assigned"},
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
        metadata={"ticket_id": ticket.get("id"), "event": "sla_breached"},
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
        metadata={"ticket_id": ticket.get("id"), "event": "escalated"},
    )


async def notify_comment_added(ticket: Dict[str, Any], author: str, preview: str) -> None:
    recipients = [r for r in _recipients(ticket) if r != author]
    if not recipients:
        return
    await _send(
        title=f"[{ticket.get('ticket_number')}] New comment by {author}",
        message=f"'{preview[:100]}...' — on ticket '{ticket.get('title', '')}'",
        severity="info",
        recipients=recipients,
        metadata={"ticket_id": ticket.get("id"), "event": "comment_added"},
    )


def _recipients(ticket: Dict[str, Any]) -> list:
    """Collect email-like strings from reporter, assignee, and watchers."""
    candidates = [
        ticket.get("reporter", ""),
        ticket.get("assignee", ""),
        *ticket.get("watchers", []),
    ]
    return list({r for r in candidates if r and "@" in r})
