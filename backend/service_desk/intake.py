"""Putting a new ticket in the desk's queue (D-01, D-04).

Called by ``POST /api/tickets`` after the ticket exists. It never raises: a failure here must not
fail the ticket (it is logged and the ticket flows as it did before the desk existed). A ticket is
queued only when a person raised it, the tenant is not the Platform tenant, the desk is not Off, the
tenant has the Autonomous Ops screen ticked (Phase 81 D-23) with a level above Off, no stop (platform or
tenant) is on, and the Tickets and Knowledge Base screens are switched on. One attempt per ticket: a
second enqueue hits the unique index and returns None. A ticket refused here is recorded nowhere and
flows as it did before the desk existed.

``tray_claim`` and ``legacy_template`` decide, for the two agent-side creation routes, whether the old
tray raised the ticket and from which template (85-09). The server decides; the client's tags are only a
claim, and a spoofed claim can only produce a draft (the old tray has no window to show an answer).
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pymongo.errors import DuplicateKeyError

from autonomous_ops import PLATFORM_TENANT_ID
from autonomous_ops import settings as ao_settings

from . import PERSON_RAISED, settings, store, ticket_writes, tray_contract

logger = logging.getLogger(__name__)

TRAY_TAG, USER_TAG, AGENT_TAG = "tray", "user-raised", "agent-raised"
WINDOWS_USER_CAP = 200


def tray_claim(tags: Any, endpoint_info: Any) -> Optional[str]:
    """The Windows user name when the legacy tray rule holds, else None.

    The rule: the request's own tags (before the route appends ``agent-raised``) contain ``tray`` and
    ``user-raised`` and not ``agent-raised``, and ``endpoint_info.username`` is a non-empty string. The
    Rust agent's create_ticket instruction (tags agent-raised and omni-agent-rust, no endpoint_info)
    never satisfies it.
    """
    if not isinstance(tags, (list, tuple)) or not isinstance(endpoint_info, dict):
        return None
    names = {t.strip().casefold() for t in tags if isinstance(t, str)}
    if TRAY_TAG not in names or USER_TAG not in names or AGENT_TAG in names:
        return None
    user = endpoint_info.get("username")
    if not isinstance(user, str) or not user.strip():
        return None
    return user.strip()[:WINDOWS_USER_CAP]


def legacy_template(title: Any) -> str:
    """The Raise a Ticket template an older tray's title prefix stands for (case-insensitive), else custom."""
    if isinstance(title, str):
        folded = title.casefold()
        for prefix, template in tray_contract.LEGACY_TITLE_PREFIXES.items():
            if folded.startswith(prefix.casefold()):
                return template
    return "custom"


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
