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

from .scope import raw

logger = logging.getLogger(__name__)

DISPATCHER = "service_desk"


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
