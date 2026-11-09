"""Shared setup for the tray route tests (Phase 85, plan 85-19): the three tenants of the portal tests plus three
enrolled agents, the real agent-key check (a signed agent token per request, so a token that names another agent
is refused by the same code production runs), and helpers that raise, seed and read tray tickets.

t1 (Post answers) has agents a1 (LAPTOP1) and a2 (LAPTOP2); t2 (Drafts only) has b1 (also LAPTOP1). Every tenant's
agents hold every capability. Real-database helpers; the local model is the stand-in of
``service_desk_support.ollama_transport``.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import httpx
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service_desk import ticket_writes, worker
from service_desk.model import OllamaClient
from tests.agent_identity_test_support import agent_token
from tests.service_desk_portal_support import ANSWER, TICKET, build_world
from tests.service_desk_support import ollama_transport

JDOE = "jdoe"
AGENTS = {"a1": ("t1", "LAPTOP1"), "a2": ("t1", "LAPTOP2"), "b1": ("t2", "LAPTOP1")}
CREATE = "/api/agents/{agent}/tray/tickets"


class TrayWorld:
    """The desk world with the tray routes mounted; ``call`` signs the request as an enrolled agent."""

    def __init__(self, desk):
        self.desk = desk
        self.db = desk.db
        self.app = desk.app

    async def call(self, method, path, *, agent="a1", json=None, params=None, headers=None):
        if headers is None:
            headers = {"Authorization": "Bearer " + agent_token(agent, AGENTS[agent][0])}
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, path, json=json, params=params, headers=headers)

    async def create(self, agent="a1", *, as_agent=None, user=JDOE, features=("my_tickets",), **extra):
        """POST the tray create route for ``agent`` (signed as ``as_agent`` when given)."""
        body = create_body(user=user, features=features, **extra)
        return await self.call("POST", CREATE.format(agent=agent), agent=as_agent or agent, json=body)

    async def list(self, agent="a1", user=JDOE):
        return await self.call("GET", CREATE.format(agent=agent), agent=agent, params={"user": user})

    async def post(self, agent, ticket, action, body):
        path = CREATE.format(agent=agent) + f"/{ticket['id']}/{action}"
        return await self.call("POST", path, agent=agent, json=body)

    async def article(self, agent, ticket, article_id, user=JDOE):
        path = CREATE.format(agent=agent) + f"/{ticket['id']}/articles/{article_id}"
        return await self.call("GET", path, agent=agent, params={"user": user})

    async def stored(self, ticket_id) -> Dict[str, Any]:
        return await self.db.tickets.find_one({"id": ticket_id}, {"_id": 0})


def create_body(*, user=JDOE, features=("my_tickets",), **extra) -> Dict[str, Any]:
    body = {"title": TICKET["title"], "description": TICKET["description"], "type": "bug", "priority": "medium",
            "template": "custom", "endpoint_info": {"hostname": "LAPTOP1", "username": user, "os_name": "Windows",
                                                    "os_version": "10.0.19045"},
            "client": {"features": list(features), "version": "2.1.18"}}
    body.update(extra)
    return body


async def build_tray_world(mongo_db, monkeypatch) -> TrayWorld:
    import agent_auth
    import agent_tasks_endpoints
    import service_desk_tray_endpoints
    from rate_limiter import agent_limiter, limiter
    original = agent_auth.get_database          # the key verify_agent_key's Depends(get_database) is registered under
    desk = await build_world(mongo_db, monkeypatch)
    for module in (service_desk_tray_endpoints, agent_tasks_endpoints):
        monkeypatch.setattr(module, "get_database", lambda: mongo_db)
    desk.app.dependency_overrides[original] = lambda: mongo_db
    desk.app.include_router(service_desk_tray_endpoints.router)
    desk.app.include_router(agent_tasks_endpoints.router)
    desk.app.state.limiter = agent_limiter
    desk.app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    agent_limiter.reset()
    limiter.reset()
    await mongo_db.tenants.update_many({}, {"$set": {"agentCapabilities": ["all"]}})
    for agent_id, (tenant, host) in AGENTS.items():
        await mongo_db.agents.insert_one({"id": agent_id, "tenantId": tenant, "hostname": host})
    return TrayWorld(desk)


async def seed_ticket(world: TrayWorld, *, tenant="t1", agent="a1", user=JDOE, my_tickets=True, title="VPN is down",
                      template="custom", age_days: Optional[float] = None) -> Dict[str, Any]:
    """A ticket of the tray, written the way the create route writes one (so the numbers and ids are real). With
    ``age_days`` its creation time is moved back that many days."""
    from tickets_service import tickets_service
    ticket = await tickets_service.create_ticket(
        data={"title": title, "description": "It drops every few minutes", "agent_id": agent,
              "tags": ["user-raised", "tray"]},
        reporter=agent, tenant_id=tenant, raised_via="tray",
        requester_channel={"tray": True, "myTickets": my_tickets, "windowsUser": user, "template": template})
    if age_days is not None:
        old = (datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat()
        await world.db.tickets.update_one({"id": ticket["id"]}, {"$set": {"created_at": old, "updated_at": old}})
    return ticket


async def say(world: TrayWorld, ticket, comment_id, kind, text, *, visibility="requester", author="Service desk",
              ai=None, at: Optional[datetime] = None) -> None:
    """One comment on the ticket, written by the desk's own writer."""
    added = await ticket_writes.add_comment(world.db, ticket["tenantId"], ticket["id"], comment_id=comment_id,
                                            kind=kind, visibility=visibility, text=text, author=author, ai=ai, now=at)
    assert added, comment_id


async def desk_pass(world: TrayWorld, *, cited=(1,), answer=ANSWER) -> None:
    """One worker pass with the stand-in model answering ``answer`` and citing ``cited``."""
    transport, _ = ollama_transport(answer, list(cited))
    await worker.run_once(world.db, client=OllamaClient(transport=transport))


async def raised_and_answered(world: TrayWorld, agent="a1", *, user=JDOE, **extra) -> Dict[str, Any]:
    """A ticket raised through the create route and answered by one desk pass. Returns the stored ticket."""
    response = await world.create(agent, user=user, **extra)
    assert response.status_code == 200, response.text
    await desk_pass(world)
    return await world.stored(response.json()["ticket_id"])
