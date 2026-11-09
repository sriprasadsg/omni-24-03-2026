"""Shared setup for the portal lifecycle tests (Phase 85, plan 85-14): a world with three tenants, a ticket the
desk has answered (a posted answer or a waiting draft) and the people around it. Real-database helpers; the
local model is the stand-in of ``service_desk_support.ollama_transport``.

t1 is set to Post answers, t2 to Drafts only and t3 to Post answers inside shadow.
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service_desk import store, worker
from service_desk.model import OllamaClient
from tests.service_desk_support import desk_app, ollama_transport, portal_user, seed_article, seed_desk_tenant

PW_TITLE = "Reset your own password"
PW_CONTENT = ("If you forgot your password, open the sign-in page and choose Forgot password. Enter your work "
              "email and follow the steps to reset your password. You can sign in again once the reset is finished.")
VPN_CONTENT = "To connect to the VPN open the client, pick the office gateway and sign in with your work account."
ANSWER = "Open the sign-in page and choose Forgot password."
TICKET = {"title": "I forgot my password",
          "description": "I cannot sign in to my laptop because I forgot my password and I need to reset it"}

ALICE = portal_user("t1", "alice@x.co")          # the reporter
BOB = portal_user("t1", "bob@x.co")              # staff
CAROL = portal_user("t1", "carol@x.co")          # more staff
DAVE = portal_user("t1", "dave@x.co")            # another tenant than the Drafts only one (t2)
DRAFT_ALICE = portal_user("t2", "alice@x.co")    # the reporter of a draft-only tenant ticket
STAFF2 = portal_user("t2", "bob@x.co")
STAFF3 = portal_user("t2", "carol@x.co")
SHADOW_ALICE = portal_user("t3", "alice@x.co")
SHADOW_STAFF = portal_user("t3", "bob@x.co")


async def build_world(mongo_db, monkeypatch):
    """Indexes, tenants, articles, the notice writer wired to the test database; returns the DeskApp."""
    from autonomous_ops import ledger
    await ledger.ensure_indexes(mongo_db)
    await store.ensure_indexes(mongo_db)
    await seed_desk_tenant(mongo_db, "t1", mode="post")
    await seed_desk_tenant(mongo_db, "t2", mode="drafts")
    await seed_desk_tenant(mongo_db, "t3", mode="post", shadow=True)
    for tenant in ("t1", "t2", "t3"):
        await seed_article(mongo_db, tenant, "kb-pw", title=PW_TITLE, content=PW_CONTENT)
        await seed_article(mongo_db, tenant, "kb-vpn", title="Connect to the VPN", content=VPN_CONTENT)
    await seed_article(mongo_db, "global", "kb-global", title=PW_TITLE, content=PW_CONTENT)
    await mongo_db.users.insert_many([{"email": "bob@x.co", "name": "Bob"}, {"email": "carol@x.co", "name": "Carol"}])
    import database
    monkeypatch.setattr(database, "get_database", lambda: mongo_db)       # the notice writer reads it per call
    import websocket_manager

    async def _ignore(tenant_id, payload):
        return None

    monkeypatch.setattr(websocket_manager, "broadcast_notification", _ignore)
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    monkeypatch.delenv("SERVICE_DESK_OLLAMA_URL", raising=False)
    monkeypatch.delenv("SERVICE_DESK_MODEL", raising=False)
    return desk_app(mongo_db, monkeypatch)


async def raise_and_run(world, user=ALICE, *, cited=(1,), answer=ANSWER):
    """The reporter raises a ticket and one worker pass answers it. Returns the stored ticket."""
    response = await world.call("POST", "/api/tickets", user=user, json=dict(TICKET))
    assert response.status_code == 200, response.text
    transport, _ = ollama_transport(answer, list(cited))
    await worker.run_once(world.db, client=OllamaClient(transport=transport))
    return await stored(world.db, response.json()["id"])


async def stored(db, ticket_id):
    return await db.tickets.find_one({"id": ticket_id}, {"_id": 0})


async def desk_row(db, ticket, tenant="t1"):
    return await db.autonomy_actions.find_one({"tenantId": tenant, "kind": "servicedesk", "command": "ticket_answer",
                                                "desk.ticketId": ticket["id"]}, {"_id": 0})


def draft_of(ticket):
    [comment] = [c for c in ticket["comments"] if c.get("kind") in ("ai_draft", "ai_answer")]
    return comment


async def notices(db, who, event=None):
    flt = {"metadata.recipient": who}
    if event:
        flt["metadata.event"] = event
    return await db.notifications.find(flt, {"_id": 0}).to_list(20)


def at(*parts):
    return datetime(*parts, tzinfo=timezone.utc)
