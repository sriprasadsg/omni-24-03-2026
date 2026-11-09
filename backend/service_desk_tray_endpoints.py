"""The service desk's tray routes (Phase 85, D-05 to D-07, D-14, D-34): the agent-key side of the My tickets window.

Five routes under ``/api/agents/{agent_id}/tray/tickets``, frozen in ``service_desk/tray_contract.py`` because the
tray script ships inside the agent. Each needs the agent's own token (``verify_agent_key`` binds the path agent
to it), the ``ticket_reporter`` capability and its own rate limit. This is the only place the staff-only versus
requester split is an enforced access boundary, so every answer is an explicit projection
(``projection.tray_view``): no route returns a stored ticket.

* create marks the ticket ``raised_via`` tray by route identity (never by a body field) and records whether this
  tray can show an answer (``myTickets``), so only a tray that can read it ever gets a posted answer;
* list, confirm, help and article act only on tickets of this tenant, raised through the tray from this agent
  (bound to the token) by this Windows user. The user name is client-reported: it separates the people who share
  one computer and is not a security boundary (D-34), and nothing here claims the list is private.

Display text comes from ``service_desk/messages.py``; the AI-assisted line above an answer is added once by the
tray script (the stored answer text carries no mark), so the server never sends it.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, field_validator

import agent_capabilities
from agent_auth import verify_agent_key
from autonomous_ops.scope import raw
from database import get_database
from rate_limiter import agent_limiter
from service_desk import intake, lifecycle, messages, projection, tray_contract
from tickets_service import tickets_service

router = APIRouter(prefix="/api/agents", tags=["Service desk tray"])
logger = logging.getLogger("service_desk_tray_endpoints")

READ_LIMIT = "30/minute"
WRITE_LIMIT = "10/minute"
USER_MAX = 256                      # characters of the reported Windows user name
FIELD_MAX = 256                     # characters of each endpoint_info value kept
SCAN_MAX = 500                      # tickets read for one list (one computer, 60 days)
UserName = Annotated[str, Field(min_length=1, max_length=USER_MAX, pattern=r"\S")]    # not blank
_ENDPOINT_KEYS = ("hostname", "username", "os_name", "os_version")
_STATUS = {"not_found": 404, "not_confirmable": 409, "help_too_long": 422}

# What the list reads of a ticket: the fields tray_view and the ownership check use, nothing else.
_READ = {"_id": 0, "id": 1, "tenantId": 1, "agent_id": 1, "raised_via": 1, "requester_channel": 1, "reporter": 1,
         "ticket_number": 1, "title": 1, "status": 1, "desk": 1, "comments": 1, "created_at": 1, "updated_at": 1}


class EndpointInfo(BaseModel):
    username: str = Field(..., max_length=USER_MAX)
    hostname: Optional[str] = Field(default=None, max_length=FIELD_MAX)
    os_name: Optional[str] = Field(default=None, max_length=FIELD_MAX)
    os_version: Optional[str] = Field(default=None, max_length=FIELD_MAX)

    @field_validator("username")
    @classmethod
    def _named(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("username is required")
        return value


class TrayClient(BaseModel):
    features: List[str] = Field(default_factory=list, max_length=20)
    version: Optional[str] = Field(default=None, max_length=64)


class TrayTicketRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=tray_contract.TITLE_MAX)
    description: Optional[str] = Field(default="", max_length=5000)
    type: Literal["bug", "feature", "task", "incident", "security"] = "task"
    priority: Literal["critical", "high", "medium", "low"] = "medium"
    template: Literal[tray_contract.TEMPLATE_IDS] = "custom"           # type: ignore[valid-type]
    endpoint_info: EndpointInfo
    client: TrayClient = Field(default_factory=TrayClient)


class ConfirmRequest(BaseModel):
    user: UserName


class HelpRequest(BaseModel):
    user: UserName
    text: Optional[str] = Field(default=None, max_length=tray_contract.NOTE_MAX)


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail=messages.API_DETAIL["not_found"])


async def _agent(tenant: Dict[str, Any], agent_id: str) -> Dict[str, Any]:
    """The calling agent's own record, found by id or hostname inside the token's tenant (404 otherwise)."""
    agent_capabilities.assert_allowed(tenant, "ticket_reporter")
    tenant_id = tenant.get("id", "")
    agent = await get_database().agents.find_one(
        {"$or": [{"id": agent_id}, {"hostname": agent_id}], "tenantId": tenant_id})
    if not agent or not tenant_id or not agent.get("id"):
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


def _scope(tenant_id: str, agent: Dict[str, Any]) -> Dict[str, Any]:
    """The tickets this computer's tray may see: this tenant, raised through a tray that can show answers from
    this agent. The Windows user is compared in code (``_is_user``)."""
    return {"tenantId": tenant_id, "agent_id": agent["id"], "raised_via": "tray",
            "requester_channel.myTickets": True}


def _is_user(ticket: Dict[str, Any], user: str) -> bool:
    channel = ticket.get("requester_channel") if isinstance(ticket.get("requester_channel"), dict) else {}
    return projection.same_person(channel.get("windowsUser"), user)


async def _own_ticket(tenant: Dict[str, Any], agent: Dict[str, Any], ticket_id: str, user: str) -> Dict[str, Any]:
    """The ticket when it belongs to this tenant, this agent and this Windows user; 404 for anything else, so a
    ticket's existence is never told to someone who does not own it."""
    ticket = await raw(get_database()).tickets.find_one(
        {**_scope(tenant.get("id", ""), agent), "id": ticket_id}, _READ)
    if ticket is None or not _is_user(ticket, user):
        raise _not_found()
    return ticket


def _refusal(result: Dict[str, Any]) -> HTTPException:
    reason = result.get("reason") or "not_found"
    text = messages.API_DETAIL.get(reason, messages.API_DETAIL["not_found"]).format(
        state="", max=lifecycle.HELP_MAX_CHARS)
    return HTTPException(status_code=_STATUS.get(reason, 409), detail=text)


@router.post("/{agent_id}/tray/tickets")
@agent_limiter.limit(WRITE_LIMIT)
async def create_tray_ticket(
    request: Request,
    response: Response,
    agent_id: str,
    body: TrayTicketRequest,
    _tenant: Dict[str, Any] = Depends(verify_agent_key),
) -> Dict[str, Any]:
    """Raise a ticket from the tray window. Who raised it is the route, not the body: the ticket is a tray
    ticket of this agent, the reporter is the agent, and the tags are set here."""
    agent = await _agent(_tenant, agent_id)
    tenant_id = _tenant["id"]
    info = {key: getattr(body.endpoint_info, key) for key in _ENDPOINT_KEYS if getattr(body.endpoint_info, key)}
    channel = {"tray": True, "myTickets": tray_contract.FEATURE_MY_TICKETS in body.client.features,
               "windowsUser": body.endpoint_info.username[:intake.WINDOWS_USER_CAP], "template": body.template}
    data = {"title": body.title, "description": body.description or "", "type": body.type,
            "priority": body.priority, "tags": ["user-raised", "tray"], "endpoint_info": info,
            "agent_id": agent["id"], "agent_hostname": agent.get("hostname") or agent["id"]}
    ticket = await tickets_service.create_ticket(data=data, reporter=agent["id"], tenant_id=tenant_id,
                                                 raised_via="tray", requester_channel=channel)
    try:
        await intake.on_ticket_created(get_database(), ticket, via="tray")
    except Exception:
        logger.exception("service desk intake failed; the ticket is unaffected")
    logger.info("Tray ticket %s created by agent %s", ticket["ticket_number"], agent["id"])
    return {"ticket_id": ticket["id"], "ticket_number": ticket["ticket_number"],
            "message": messages.TRAY_CREATED.format(number=ticket["ticket_number"])}


@router.get("/{agent_id}/tray/tickets")
@agent_limiter.limit(READ_LIMIT)
async def list_tray_tickets(
    request: Request,
    response: Response,
    agent_id: str,
    user: str = Query(..., min_length=1, max_length=USER_MAX, pattern=r"\S"),
    _tenant: Dict[str, Any] = Depends(verify_agent_key),
) -> Dict[str, Any]:
    """My tickets: up to 20 tickets of the last 60 days, newest first, raised from this computer by this
    Windows user, as the tray's projection."""
    agent = await _agent(_tenant, agent_id)
    user = user.strip()
    since = (datetime.now(timezone.utc) - timedelta(days=tray_contract.LIST_DAYS)).isoformat()
    cursor = raw(get_database()).tickets.find(
        {**_scope(_tenant["id"], agent), "created_at": {"$gte": since}}, _READ).sort("created_at", -1).limit(SCAN_MAX)
    shown: List[Dict[str, Any]] = []
    async for ticket in cursor:
        if _is_user(ticket, user):
            shown.append(projection.tray_view(ticket))
            if len(shown) == tray_contract.LIST_LIMIT:
                break
    return {"tickets": shown, "user": user, "display": projection.tray_display(user)}


@router.post("/{agent_id}/tray/tickets/{ticket_id}/confirm")
@agent_limiter.limit(WRITE_LIMIT)
async def confirm_tray_ticket(
    request: Request,
    response: Response,
    agent_id: str,
    ticket_id: str,
    body: ConfirmRequest,
    _tenant: Dict[str, Any] = Depends(verify_agent_key),
) -> Dict[str, Any]:
    """This fixed it: the same lifecycle as the portal button, for a ticket this user raised from this computer."""
    agent = await _agent(_tenant, agent_id)
    await _own_ticket(_tenant, agent, ticket_id, body.user)
    result = await lifecycle.confirm(get_database(), _tenant["id"], ticket_id,
                                     requester={"id": "tray:" + agent["id"], "name": body.user.strip()})
    if result.get("status") == "refused":
        raise _refusal(result)
    return result


@router.post("/{agent_id}/tray/tickets/{ticket_id}/help")
@agent_limiter.limit(WRITE_LIMIT)
async def help_tray_ticket(
    request: Request,
    response: Response,
    agent_id: str,
    ticket_id: str,
    body: HelpRequest,
    _tenant: Dict[str, Any] = Depends(verify_agent_key),
) -> Dict[str, Any]:
    """I still need help: the same lifecycle as the portal button, with the optional note of up to 500 characters."""
    agent = await _agent(_tenant, agent_id)
    await _own_ticket(_tenant, agent, ticket_id, body.user)
    result = await lifecycle.still_need_help(get_database(), _tenant["id"], ticket_id,
                                             requester={"id": "tray:" + agent["id"], "name": body.user.strip()},
                                             text=body.text)
    if result.get("status") == "refused":
        raise _refusal(result)
    return result


@router.get("/{agent_id}/tray/tickets/{ticket_id}/articles/{article_id}")
@agent_limiter.limit(READ_LIMIT)
async def read_tray_article(
    request: Request,
    response: Response,
    agent_id: str,
    ticket_id: str,
    article_id: str,
    user: str = Query(..., min_length=1, max_length=USER_MAX, pattern=r"\S"),
    _tenant: Dict[str, Any] = Depends(verify_agent_key),
) -> Dict[str, Any]:
    """Read one article cited on this ticket's answer (D-14): only an article cited on an answer the requester
    can still read, from this tenant's own Help desk set, never the global set. A cited article that was deleted
    since answers ``available`` false."""
    agent = await _agent(_tenant, agent_id)
    ticket = await _own_ticket(_tenant, agent, ticket_id, user)
    cited = projection.cited_articles(ticket, for_requester=True)
    if article_id not in cited:
        raise HTTPException(status_code=404, detail=messages.API_DETAIL["article_not_found"])
    doc = await raw(get_database()).knowledge_docs.find_one(
        {"id": article_id, "tenantId": _tenant["id"], "helpdesk": True}, {"_id": 0, "title": 1, "content": 1})
    if doc is None:
        return {"title": cited[article_id], "content": "", "available": False}
    return {"title": doc["title"] if isinstance(doc.get("title"), str) else cited[article_id],
            "content": doc["content"] if isinstance(doc.get("content"), str) else "", "available": True}
