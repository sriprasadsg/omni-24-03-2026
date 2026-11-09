"""The one ticket-staff test of the platform (Phase 85 gap G-85-4, WR-502).

"Ticket staff" means a signed-in person who handles other people's tickets as IT staff. Until
this module existed "not the reporter" stood in for "staff", so any requester who was not the
reporter of a ticket counted as one. The marker is now the permission ``manage:tickets``: the
built-in roles tenant_admin (alias admin), analyst, security_analyst and incident_responder hold
it, the super-admin wildcard reaches it, and a custom role holds it only when its own role
document lists it. Everybody else (user, viewer, platform_support, a custom role without the
permission) is a requester.

Later gap plans add the ticket viewer guard and the own-tickets scope here. Module-level imports
are limited to ``typing`` and ``rbac_service`` so the ticket and notification modules can import
this one without a cycle.
"""
from typing import Iterable, Optional

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
