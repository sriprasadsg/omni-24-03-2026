"""Three working days without a reply: the ticket goes back to a person (D-08, D-31).

An answer the desk posted, or a draft a person sent, leaves the ticket ``pending_customer`` and waits for the
requester. When 3 working days (Monday to Friday, counted in the tenant's time zone) have passed since
``desk.postedAt`` and nobody has answered, ``sweep_due`` moves the ticket back to ``open``, hands it to a person
through the one hand-off path (reason ``no_reply_to_ai_answer``, with the requester notice), marks
``desk.phase`` ``returned`` and records the return on the answer's own row. It never resolves or closes a
ticket for the requester (PROH-85-04), and it leaves ``desk.undoable`` exactly as it was.

The due time is worked out from ``desk.postedAt`` every time, the same way the requester's panel shows it
(``projection.return_at``); nothing is stored in advance. A ticket someone already moved (confirmed, helped,
withdrawn, reopened by a person) is not ``pending_customer`` any more and is never returned. Every query names
its tenant; a failure on one ticket or tenant is logged and the next one still runs.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from autonomous_ops import ledger
from autonomous_ops.scope import raw

from . import RETURN_WORKING_DAYS, SYSTEM_AUTHOR, handoff, ticket_writes, workdays

logger = logging.getLogger(__name__)

ANSWERED_PHASES = ("posted", "sent")
PER_TENANT_LIMIT = 500
# The query only narrows the candidates; the exact time is worked out per ticket. Three working days are at least
# three calendar days apart in local time, and a change of daylight saving time moves that by an hour or two, so
# the narrowing leaves a whole day of margin.
_PREFILTER_DAYS = RETURN_WORKING_DAYS - 1


def _aware(value: Any) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


async def _step(label: str, ticket_id: str, awaitable) -> None:
    """One write of the return; a failing write is logged and the rest still runs."""
    try:
        await awaitable
    except Exception as exc:
        logger.error("service_desk: the %s of ticket %s was not saved: %s", label, ticket_id, exc)


async def _return_ticket(db, ticket: Dict[str, Any], now: datetime) -> bool:
    """Give one ticket back to a person. False when it moved on its own before we got to it."""
    tenant, ticket_id = ticket["tenantId"], ticket["id"]
    moved = await ticket_writes.move_status(db, tenant, ticket_id, ("pending_customer",), "open",
                                            actor=SYSTEM_AUTHOR, now=now)
    if not moved:
        return False
    fresh = await raw(db).tickets.find_one({"id": ticket_id, "tenantId": tenant}, {"_id": 0}) or ticket
    await _step("hand-off", ticket_id, handoff.handoff(db, fresh, "no_reply_to_ai_answer", now=now))
    await _step("desk fields", ticket_id, ticket_writes.set_desk(
        db, tenant, ticket_id, {"phase": "returned", "returnedAt": now}, now=now))
    action_id = (ticket.get("desk") or {}).get("actionId")
    if action_id:
        await _step("Activity row", ticket_id, ledger.set_desk_fields(
            db, tenant, action_id, {"phase": "returned", "returnedAt": now}, event="returned"))
    return True


async def _sweep_tenant(db, tenant: str, now: datetime, counts: Dict[str, int]) -> None:
    zone = await workdays.tenant_zone(db, tenant)
    candidates = await raw(db).tickets.find(
        {"tenantId": tenant, "desk.phase": {"$in": list(ANSWERED_PHASES)}, "status": "pending_customer",
         "desk.postedAt": {"$lte": now - timedelta(days=_PREFILTER_DAYS)}}, {"_id": 0}
    ).sort([("desk.postedAt", 1), ("id", 1)]).to_list(PER_TENANT_LIMIT)
    for ticket in candidates:
        posted = _aware((ticket.get("desk") or {}).get("postedAt"))
        if posted is None or workdays.add_working_days(posted, RETURN_WORKING_DAYS, zone) > now:
            continue
        try:
            if await _return_ticket(db, ticket, now):
                counts["returned"] += 1
        except Exception as exc:
            counts["failed"] += 1
            logger.error("service_desk: ticket %s could not be returned to a person: %s", ticket.get("id"), exc)


async def sweep_due(db, *, now: datetime) -> Dict[str, int]:
    """Return every answered ticket whose requester has been silent for 3 working days (in the tenant's zone) to a
    person. Safe to run twice or from two runners: the status change is a compare-and-set, so a ticket is
    returned once. Returns ``{"returned": n, "failed": n}``."""
    now = _aware(now) or datetime.now(timezone.utc)
    counts = {"returned": 0, "failed": 0}
    tenants = await raw(db).tenants.find({}, {"_id": 0, "id": 1}).to_list(None)
    for entry in tenants:
        tenant = entry.get("id")
        if not isinstance(tenant, str) or not tenant:
            continue
        try:
            await _sweep_tenant(db, tenant, now, counts)
        except Exception as exc:
            counts["failed"] += 1
            logger.error("service_desk: the return sweep failed for tenant %s: %s", tenant, exc)
    return counts
