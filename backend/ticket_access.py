"""The one ticket-staff test of the platform (Phase 85 gap G-85-4, WR-502).

"Ticket staff" means a signed-in person who handles other people's tickets as IT staff. Until
this module existed "not the reporter" stood in for "staff", so any requester who was not the
reporter of a ticket counted as one. The marker is now the permission ``manage:tickets``: the
built-in roles tenant_admin (alias admin), analyst, security_analyst and incident_responder hold
it, the super-admin wildcard reaches it, and a custom role holds it only when its own role
document lists it. Everybody else (user, viewer, platform_support, a custom role without the
permission) is a requester.

``ticket_viewer`` (plan 85-32, WR-502) is the router guard of the ticket routes: only ticket staff and
the ticket's reporter reach a ticket at all. A later gap plan adds the own-tickets scope here.
Module-level imports are limited to ``typing``, ``fastapi`` and ``rbac_service`` (plus
``authentication_service`` for the caller); the ticket modules are imported inside the guard so the
ticket and notification modules can import this one without a cycle.
"""
import re
from typing import Any, Dict, Iterable, Optional

from fastapi import Depends, HTTPException, Request

from authentication_service import get_current_user
from rbac_service import rbac_service

TICKET_STAFF = "manage:tickets"


def holds_ticket_staff(perms: Optional[Iterable[str]]) -> bool:
    """True when ``perms`` (granted permissions) hold the wildcard or ``manage:tickets``."""
    held = set(perms or ())
    return "*" in held or TICKET_STAFF in held


async def is_ticket_staff(user, perms: Optional[Iterable[str]] = None) -> bool:
    """Whether ``user`` handles tickets as IT staff.

    The same two checks ``rbac_service.has_permission`` makes for a permission: the granted
    permissions first (fetched through ``get_user_permissions`` only when ``perms`` is not
    given, which already falls back to the built-in table when the role store is unreachable),
    then the API-key scopes, which can only narrow. False otherwise.
    """
    if perms is None:
        perms = await rbac_service.get_user_permissions(user)
    return holds_ticket_staff(perms) and rbac_service._scopes_allow(user, TICKET_STAFF)


def ticket_viewer(detail: str = "Ticket not found"):
    """A router dependency: a route with a ``ticket_id`` path parameter answers 404 ``detail`` unless the
    caller is ticket staff or the ticket's reporter (WR-502, PROH-85-23).

    It is the same 404 as for a ticket that does not exist (never 403), so a requester cannot learn that
    someone else's ticket id is real. Staff skip the ticket read; everybody else is checked against the
    ticket of their own tenant (no tenant means no ticket). A route without ``ticket_id`` is not touched.
    """
    async def guard(request: Request, current_user=Depends(get_current_user)) -> None:
        ticket_id = request.path_params.get("ticket_id")
        if ticket_id is None or await is_ticket_staff(current_user):
            return
        import tickets_models
        import tickets_service
        from service_desk import projection
        tenant_id = tickets_models._effective_tenant(current_user)
        ticket = await tickets_service.tickets_service.get_ticket(ticket_id, tenant_id=tenant_id) if tenant_id else None
        if not ticket or not projection.is_reporter(ticket, current_user):
            raise HTTPException(status_code=404, detail=detail)

    return guard


def own_tickets_filter(user) -> Dict[str, Any]:
    """A MongoDB filter for the tickets ``user`` raised: the reporter equals the username or the email,
    ignoring case. Each name is an anchored, escaped pattern, so regex characters in a name match only
    themselves; a caller with no name gets an empty ``$in``, which matches nothing."""
    names = {str(getattr(user, field, "") or "").strip() for field in ("username", "email")} - {""}
    return {"reporter": {"$in": [re.compile(f"^{re.escape(name)}$", re.IGNORECASE) for name in sorted(names)]}}


async def tickets_scope(user) -> Optional[Dict[str, Any]]:
    """The query restriction for ticket lists, counts, reports and exports (UD-2, PROH-85-24): None for ticket
    staff (the whole tenant), the caller's own-tickets filter for everybody else. It belongs in the database
    query, never applied to the rows afterwards, so totals, pages and statistics agree with what is shown."""
    return None if await is_ticket_staff(user) else own_tickets_filter(user)
