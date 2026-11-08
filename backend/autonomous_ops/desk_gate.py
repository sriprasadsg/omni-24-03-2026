"""The service desk's place in the gate (Phase 85, DESK-01): the ownership step for a ticket action.

``ticket_answer`` acts on a ticket, never on an agent, so the gate's agent target check does not apply
to it. ``gate._step_protected_targets`` hands a request from the ``service_desk`` dispatcher to
``ticket_owner_step`` instead: the request names no agent, carries the ticket id in its params, and the
ticket must belong to the caller's own tenant. Anything else is refused and nothing is dispatched.

Raw Mongo handle with an explicit tenantId; the ambient tenant ContextVar is never used. This module
imports nothing from the service desk package (the dispatcher name is a string constant on both sides)
and no LLM client.
"""
import logging

from . import RATE_LIMIT_WINDOW, ledger
from .scope import raw

logger = logging.getLogger(__name__)

DISPATCHER = "service_desk"
DESK_RATE_LIMIT = 20      # D-30: automatic desk answers per rolling hour (the same value as service_desk.DESK_RATE_LIMIT)


async def ticket_owner_step(ctx) -> None:
    """Refuse unless the request names no agent and a ticket of the request's tenant.

    Codes: ``invalid_target`` (an agent target was given), ``no_target`` (no ticket id),
    ``cross_tenant_target`` (the ticket is missing or belongs to another tenant) and
    ``protected_target`` (the ticket could not be read: fail closed)."""
    req = ctx.req
    if req.targets:
        return ctx.refuse("protected_targets", "invalid_target")
    params = req.params if isinstance(req.params, dict) else {}
    ticket_id = params.get("ticketId")
    if not isinstance(ticket_id, str) or not ticket_id:
        return ctx.refuse("protected_targets", "no_target")
    try:
        found = await raw(ctx.db).tickets.find_one({"id": ticket_id, "tenantId": req.tenant_id}, {"_id": 0, "id": 1})
    except Exception as exc:
        logger.error("autonomous_ops: ticket %s could not be read, refusing: %s", ticket_id, exc)
        return ctx.refuse("protected_targets", "protected_target")
    if found is None:
        return ctx.refuse("protected_targets", "cross_tenant_target")
    ctx.note("protected_targets", "pass")


async def rate_step(ctx) -> None:
    """D-30: the desk's own hourly pool. The 21st automatic answer in a rolling hour is a draft (suggest),
    never an approval card, and nobody is told: no notification and no on-call notice (D-22, PROH-85-07).
    An unreadable count is treated as full (fail closed). The desk answers one ticket, never a host, so the
    host cap does not apply."""
    if ctx.strongest()[0] == "allow_auto":
        try:
            recent = await ledger.count_auto_since(ctx.db, ctx.req.tenant_id, ctx.now - RATE_LIMIT_WINDOW, pool="servicedesk")
        except Exception as exc:
            logger.error("autonomous_ops: desk rate limit unreadable, drafting instead: %s", exc)
            recent = DESK_RATE_LIMIT
        if recent >= DESK_RATE_LIMIT:
            return ctx.escalate("blast_radius", "suggest", "desk_rate_limit")
    ctx.note("blast_radius", "pass")
