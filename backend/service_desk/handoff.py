"""The one way the desk sends a ticket to a person (D-24).

Every escalation path ends here: the rules, no match, the model offline or busy, a failed output check,
"I still need help", no reply, a withdrawn answer, a stop. A hand-off

* sends an unassigned ticket through the tenant's own queue rules (the same ``auto_assign`` a new ticket
  goes through) and never changes an assignee that is already set;
* adds one staff-only note naming the reason and, unless there is no one to read it, one plain notice
  for the requester that never names the reason (T-85-42);
* marks the ticket ``desk.phase = handed_off`` and keeps the reason in ``desk.lastReason``;
* writes one audited ledger row (D-24).

It pages no one and never raises the ticket's priority (D-22, T-85-43). Each step is wrapped on its own, so a
failing write is logged and the rest still runs: the ticket must reach a person. Calling it again for the
same ticket and reason adds nothing.
"""
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from autonomous_ops import ledger
from autonomous_ops.scope import raw, tenant_scope
from service_desk import HANDOFF_REASONS, SYSTEM_AUTHOR, messages, projection, ticket_writes

logger = logging.getLogger(__name__)


async def _assign(db, ticket: Dict[str, Any], tenant: str, ticket_id: str) -> None:
    """Route an unassigned ticket by the tenant's queue rules. The stored assignee is read fresh, so a person
    who took the ticket after the caller read it is never overridden."""
    assignee = ticket.get("assignee")
    stored = await raw(db).tickets.find_one({"id": ticket_id, "tenantId": tenant}, {"_id": 0, "assignee": 1})
    if stored is not None:
        assignee = stored.get("assignee")
    if assignee:
        return
    from tickets_service import tickets_service
    with tenant_scope(tenant):
        assigned = await tickets_service.auto_assign(ticket)
        if assigned:
            await tickets_service.update_ticket(ticket_id, {"assignee": assigned}, actor="system", tenant_id=tenant)


async def handoff(db, ticket: Dict[str, Any], reason: str, *, now: Optional[datetime] = None,
                  notify_requester: bool = True, actor: Optional[Dict[str, Any]] = None) -> bool:
    """Send ``ticket`` to a person for ``reason`` (one of ``HANDOFF_REASONS``; ValueError otherwise).
    True when this call recorded the hand-off, False when it had been recorded before."""
    if reason not in HANDOFF_REASONS:
        raise ValueError(f"not a hand-off reason: {reason!r}")
    tenant, ticket_id = ticket.get("tenantId"), ticket.get("id")
    if not (isinstance(tenant, str) and tenant and isinstance(ticket_id, str) and ticket_id):
        raise ValueError("a hand-off needs a ticket with an id and a tenantId")
    label = messages.STAFF_REASON_LABELS[reason]
    number = ticket.get("ticket_number") or ""

    try:
        await _assign(db, ticket, tenant, ticket_id)
    except Exception as exc:
        logger.error("service_desk: ticket %s could not be assigned by the queue rules: %s", ticket_id, exc)

    is_new = True
    try:
        is_new = await ticket_writes.add_comment(
            db, tenant, ticket_id, comment_id=f"sd-note-{reason}-{ticket_id}", kind="staff_note",
            visibility="staff", text=messages.STAFF_NOTE.format(label=label), author=SYSTEM_AUTHOR, now=now)
    except Exception as exc:
        logger.error("service_desk: the staff note for ticket %s was not saved: %s", ticket_id, exc)
    if not is_new:
        return False

    if reason != "desk_stopped" and notify_requester and projection.can_see(ticket):
        try:
            await ticket_writes.add_comment(
                db, tenant, ticket_id, comment_id=f"sd-notice-{reason}-{ticket_id}", kind="handoff_notice",
                visibility="requester", text=messages.HANDOFF_NOTICE, author=SYSTEM_AUTHOR, now=now)
        except Exception as exc:
            logger.error("service_desk: the notice for ticket %s was not saved: %s", ticket_id, exc)

    try:
        await ticket_writes.set_desk(db, tenant, ticket_id,
                                     {"phase": "handed_off", "lastReason": reason, "draftWaiting": False}, now=now)
    except Exception as exc:
        logger.error("service_desk: ticket %s was not marked handed off: %s", ticket_id, exc)

    try:
        await ledger.record_desk_event(
            db, tenant, ticket=ticket, reason_code=reason, reason_text=messages.sentence(label),
            activity_result=messages.ACTIVITY["handoff_result"].format(number=number), actor=actor, now=now)
    except Exception as exc:
        logger.error("service_desk: the hand-off of ticket %s was not recorded: %s", ticket_id, exc)
    return True
