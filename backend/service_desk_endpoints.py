"""The requester's view of the service desk on a ticket (DESK-01). 85-14 expands it.

``GET /api/tickets/{ticket_id}/service-desk``: the ticket is read inside the caller's own tenant (any
other ticket answers 404), and only the person who raised it gets the requester block. Everyone else
in the tenant gets ``isRequester`` false and no requester items, so a draft or a staff note is never
returned from here.
"""
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from authentication_service import TokenData
from rbac_service import rbac_service
from service_desk import projection
from tickets_models import _effective_tenant
from tickets_service import tickets_service

router = APIRouter(prefix="/api/tickets", tags=["Service desk"])


def _is_requester(ticket: Dict[str, Any], user: TokenData) -> bool:
    reporter = ticket.get("reporter")
    if not isinstance(reporter, str) or not reporter.strip():
        return False
    names = {str(getattr(user, field, "") or "").strip().casefold() for field in ("username", "email")}
    return reporter.strip().casefold() in names - {""}


@router.get("/{ticket_id}/service-desk")
async def get_service_desk(
    ticket_id:    str,
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
) -> Dict[str, Any]:
    tenant_id = _effective_tenant(current_user)
    ticket = await tickets_service.get_ticket(ticket_id, tenant_id=tenant_id) if tenant_id else None
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    is_requester = _is_requester(ticket, current_user)
    return {
        "ticketId": ticket.get("id"), "ticketNumber": ticket.get("ticket_number"), "status": ticket.get("status"),
        "isRequester": is_requester,
        "requester": ({"items": projection.requester_items(ticket), "canSee": projection.can_see(ticket)}
                      if is_requester else None),
    }
