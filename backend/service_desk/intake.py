"""Putting a new ticket in the desk's queue (D-01, D-04).

Called by ``POST /api/tickets`` after the ticket exists. It never raises: a failure here must not
fail the ticket (it is logged and the ticket flows as it did before the desk existed). A ticket is
queued only when a person raised it, the tenant is not the Platform tenant, the desk is not Off and
the tenant has the Autonomous Ops screen ticked (Phase 81 D-23). One attempt per ticket: a second
enqueue hits the unique index and returns None. 85-09 adds the level, stop and screen checks.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pymongo.errors import DuplicateKeyError

from autonomous_ops import PLATFORM_TENANT_ID
from autonomous_ops import settings as ao_settings

from . import PERSON_RAISED, settings, store, ticket_writes

logger = logging.getLogger(__name__)


async def on_ticket_created(db, ticket: Dict[str, Any], *, via: str,
                            now: Optional[datetime] = None) -> Optional[str]:
    """Queue ``ticket`` for one attempt. Returns the job id, or None when nothing was queued."""
    try:
        tenant = ticket.get("tenantId")
        ticket_id = ticket.get("id")
        if not isinstance(tenant, str) or not tenant or tenant == PLATFORM_TENANT_ID:
            return None
        if not isinstance(ticket_id, str) or not ticket_id or via not in PERSON_RAISED:
            return None
        if (await settings.load(db, tenant)).mode == "off":
            return None
        if not (await ao_settings.load(db, tenant)).eligible:
            return None
        now = now or datetime.now(timezone.utc)
        job_id = "SDJ-" + uuid.uuid4().hex
        job = {"id": job_id, "tenantId": tenant, "ticketId": ticket_id, "ticketNumber": ticket.get("ticket_number"),
               "createdAt": now, "state": "pending", "startedAt": None, "finishedAt": None, "reason": None}
        try:
            await store.jobs(db).insert_one(job)
        except DuplicateKeyError:
            return None
        await ticket_writes.set_desk(db, tenant, ticket_id, {"phase": "queued", "jobId": job_id}, now=now)
        return job_id
    except Exception as exc:
        logger.error("service_desk: ticket could not be queued: %s", exc)
        return None
