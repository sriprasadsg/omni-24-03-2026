"""The portal's service desk routes on a ticket (DESK-01): the view, and what staff and the requester do.

``GET /api/tickets/{ticket_id}/service-desk``: the ticket is read inside the caller's own tenant (any other
ticket answers 404). The reporter gets the requester block and never a draft; everyone else in the tenant gets
the staff draft panel and no requester block, so a draft or a staff note is never returned to the requester.
Staff send, edit or discard a waiting draft (D-09, D-10); the reporter confirms the answer or asks for a person
(D-07, D-31); every refusal reads the text of ``messages.API_DETAIL``. Every route needs ``view:dashboard``;
who is the reporter and who is staff is decided per ticket, never by the client.
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from authentication_service import TokenData
from autonomous_ops import ledger
from autonomous_ops.scope import raw
from database import get_database
from rbac_service import rbac_service
from service_desk import ANSWER_MAX_CHARS, lifecycle, messages, projection, workdays
from tickets_models import _effective_tenant
from tickets_service import tickets_service

router = APIRouter(prefix="/api/tickets", tags=["Service desk"])

_STATUS = {"not_found": 404, "already_handled": 409, "ticket_closed": 409, "person_replied": 409,
           "no_requester": 409, "not_confirmable": 409, "draft_empty": 422, "draft_too_long": 422,
           "edit_unchanged": 422, "help_too_long": 422}


class HelpNote(BaseModel):
    text: Optional[str] = Field(default=None, max_length=20000)     # a body bound only; 1000 is checked with its own text


class DraftEdit(BaseModel):
    text: str = Field(max_length=20000)     # a body bound only; the answer limit is checked with its own text


async def _ticket(ticket_id: str, user: TokenData) -> Dict[str, Any]:
    tenant_id = _effective_tenant(user)
    ticket = await tickets_service.get_ticket(ticket_id, tenant_id=tenant_id) if tenant_id else None
    if not ticket:
        raise HTTPException(status_code=404, detail=messages.API_DETAIL["not_found"])
    return ticket


async def _actor(db, user: TokenData) -> Dict[str, Any]:
    """{id, name} of the caller: the user name, and the profile name when there is one."""
    username = str(user.username or "unknown")
    name = username
    try:
        doc = await raw(db).users.find_one({"email": username}, {"_id": 0, "name": 1})
        if doc and isinstance(doc.get("name"), str) and doc["name"].strip():
            name = doc["name"].strip()
    except Exception:           # the name is a courtesy; the user name always works
        pass
    return {"id": username, "name": name}


def _refusal(result: Dict[str, Any]) -> HTTPException:
    reason = result.get("reason") or "not_found"
    limit = lifecycle.HELP_MAX_CHARS if reason == "help_too_long" else ANSWER_MAX_CHARS
    text = messages.API_DETAIL.get(reason, messages.API_DETAIL["not_found"]).format(
        state=result.get("state") or "", max=limit)
    return HTTPException(status_code=_STATUS.get(reason, 409), detail=text)


def _staff_only(ticket: Dict[str, Any], user: TokenData) -> None:
    if projection.is_reporter(ticket, user):
        raise HTTPException(status_code=403, detail=messages.API_DETAIL["staff_only"])


@router.get("/{ticket_id}/service-desk")
async def get_service_desk(
    ticket_id:    str,
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
) -> Dict[str, Any]:
    ticket = await _ticket(ticket_id, current_user)
    db = get_database()
    is_requester = projection.is_reporter(ticket, current_user)
    draft: Optional[Dict[str, Any]] = None
    waiting = projection.waiting_draft(ticket)
    if waiting is not None and not is_requester:
        action_id = waiting["ai"].get("actionId")
        row = await ledger.get(db, ticket["tenantId"], action_id) if action_id else None
        draft = projection.staff_view(ticket, row, current_user)
    zone = await workdays.tenant_zone(db, ticket["tenantId"])
    return {
        "ticketId": ticket.get("id"), "ticketNumber": ticket.get("ticket_number"), "status": ticket.get("status"),
        "isRequester": is_requester,
        "requester": projection.requester_view(ticket, zone) if is_requester else None,
        "draft": draft,
        "canReplyToRequester": (not is_requester) and projection.can_reply(ticket),
        "draftWaiting": draft is not None,
    }


async def _draft_action(ticket_id: str, comment_id: str, user: TokenData, act, **kwargs) -> Dict[str, Any]:
    ticket = await _ticket(ticket_id, user)
    _staff_only(ticket, user)
    db = get_database()
    result = await act(db, ticket["tenantId"], ticket_id, comment_id, actor=await _actor(db, user), **kwargs)
    if result.get("status") == "refused":
        raise _refusal(result)
    return result


@router.post("/{ticket_id}/service-desk/drafts/{comment_id}/send")
async def send_draft(
    ticket_id:    str,
    comment_id:   str,
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
) -> Dict[str, Any]:
    return await _draft_action(ticket_id, comment_id, current_user, lifecycle.send_draft)


@router.post("/{ticket_id}/service-desk/drafts/{comment_id}/edit")
async def edit_and_send_draft(
    ticket_id:    str,
    comment_id:   str,
    body:         DraftEdit,
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
) -> Dict[str, Any]:
    return await _draft_action(ticket_id, comment_id, current_user, lifecycle.send_draft, text=body.text)


@router.post("/{ticket_id}/service-desk/drafts/{comment_id}/discard")
async def discard_draft(
    ticket_id:    str,
    comment_id:   str,
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
) -> Dict[str, Any]:
    return await _draft_action(ticket_id, comment_id, current_user, lifecycle.discard_draft)


def _reporter_only(ticket: Dict[str, Any], user: TokenData) -> None:
    if not projection.is_reporter(ticket, user):
        raise HTTPException(status_code=403, detail=messages.API_DETAIL["not_requester"])


@router.post("/{ticket_id}/service-desk/confirm")
async def confirm_fixed(
    ticket_id:    str,
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
) -> Dict[str, Any]:
    """This fixed it: only the person who raised the ticket, and only while an answer waits on them."""
    ticket = await _ticket(ticket_id, current_user)
    _reporter_only(ticket, current_user)
    db = get_database()
    result = await lifecycle.confirm(db, ticket["tenantId"], ticket_id, requester=await _actor(db, current_user))
    if result.get("status") == "refused":
        raise _refusal(result)
    return result


@router.post("/{ticket_id}/service-desk/help")
async def still_need_help(
    ticket_id:    str,
    body:         Optional[HelpNote] = None,
    current_user: TokenData = Depends(rbac_service.has_permission("view:dashboard")),
) -> Dict[str, Any]:
    """I still need help: the ticket goes to a person; the note is optional (up to 1000 characters)."""
    ticket = await _ticket(ticket_id, current_user)
    _reporter_only(ticket, current_user)
    db = get_database()
    result = await lifecycle.still_need_help(db, ticket["tenantId"], ticket_id, requester=await _actor(db, current_user),
                                             text=body.text if body else None)
    if result.get("status") == "refused":
        raise _refusal(result)
    return result
