"""Comment visibility and the notice leaks (Phase 85, plan 85-08, DESK-01, decisions D-11 and D-33). Real
MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py.

Value: protects=a comment is staff-only unless a technician chooses Reply to requester, that choice is refused
where no requester can read it, and staff-only text never reaches the reporter or the tenant-wide feed through
a comment notice, a history entry or the requester projection; a notice meant for one person is read only by
that person; fails_when=a staff comment is stored without the flag, a reply to an automated ticket is accepted,
a notice of a staff-only comment carries its text or addresses the reporter, a recipient-tagged notice reaches
another user, or an untagged notice stops reaching the tenant; no_claim=the notice the desk sends when it
answers (85-12) and the tray routes (85-19).
"""
import asyncio
import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth_types import TokenData
from service_desk import messages, projection, store
from tenant_context import reset_tenant_id, set_tenant_id
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.service_desk_support import desk_app, portal_user, seed_desk_tenant, staff_user

SECRET = "the admin password is hunter2-staff-only"
REPLY = "Please restart the laptop and try again"
ALICE = portal_user("t1", "alice@x.co")           # the reporter
BOB = staff_user("t1", "bob@x.co")                # the assigned technician (staff, manage:tickets)
CAROL = staff_user("t1", "carol@x.co")              # staff (manage:tickets)
OTHER_ALICE = portal_user("t2", "alice@x.co")
TICKET = {"title": "My laptop will not start", "description": "It shows a black screen", "assignee": "bob@x.co"}


@pytest.fixture
async def world(mongo_db, monkeypatch):  # noqa: F811
    await store.ensure_indexes(mongo_db)
    await seed_desk_tenant(mongo_db, "t1")
    await seed_desk_tenant(mongo_db, "t2")
    import database
    monkeypatch.setattr(database, "get_database", lambda: mongo_db)       # the notice writer reads it per call
    import websocket_manager
    pushed = []                                                            # what the tenant-wide socket would carry

    async def _capture(tenant_id, payload):
        pushed.append({"tenant": tenant_id, **payload})

    monkeypatch.setattr(websocket_manager, "broadcast_notification", _capture)
    app = desk_app(mongo_db, monkeypatch)
    app.pushed = pushed
    return app


async def _drain():
    """Let the background notice tasks finish, as the live server's loop would."""
    pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if pending:
        await asyncio.wait(pending, timeout=3)


async def _raise(world, user=ALICE, **extra):
    response = await world.call("POST", "/api/tickets", user=user, json={**TICKET, **extra})
    assert response.status_code == 200, response.text
    return response.json()


async def _comment(world, ticket_id, text, *, user=BOB, **extra):
    return await world.call("POST", f"/api/tickets/{ticket_id}/comments", user=user, json={"text": text, **extra})


async def _stored(db, ticket_id):
    return await db.tickets.find_one({"id": ticket_id}, {"_id": 0})


async def _feed(db, user, *, perms=("view:dashboard",), tenant="t1"):
    """GET /api/notifications as ``user`` (the function the route runs, permissions stubbed)."""
    import notification_endpoints as ne
    from database import TenantIsolatedDatabase
    token = set_tenant_id(tenant)
    try:
        with patch.object(ne, "get_database", return_value=TenantIsolatedDatabase(db)):
            with patch.object(ne.rbac_service, "get_user_permissions", AsyncMock(return_value=list(perms))):
                return await ne.get_notifications(current_user=user, limit=50)
    finally:
        reset_tenant_id(token)


# ---------------------------------------------------------------- Task 1: the visibility flag

async def test_a_comment_is_staff_only_unless_the_technician_chooses_the_requester(world):
    """protects=D-11 default; fails_when=a comment without the choice is stored requester-visible, the choice is
    ignored, or a value outside the two is accepted."""
    ticket = await _raise(world)
    assert (await _comment(world, ticket["id"], SECRET)).status_code == 200
    assert (await _comment(world, ticket["id"], REPLY, visibility="requester")).status_code == 200
    assert (await _comment(world, ticket["id"], "x", visibility="staff")).status_code == 200
    bad = await _comment(world, ticket["id"], "x", visibility="other")
    assert bad.status_code == 422
    stored = await _stored(world.db, ticket["id"])
    assert [(c["text"], c["visibility"]) for c in stored["comments"]] == [
        (SECRET, "staff"), (REPLY, "requester"), ("x", "staff")]


async def test_a_reply_to_an_automated_ticket_is_refused_but_a_staff_note_is_not(world):
    """protects=D-11 no_reply_target for raised_via automation; fails_when=the reply is stored or the refusal
    text differs from the table."""
    ticket = await _raise(world, user=portal_user("t1", "key", auth_source="api_key"))
    assert (await _stored(world.db, ticket["id"]))["raised_via"] == "automation"
    refused = await _comment(world, ticket["id"], REPLY, visibility="requester")
    assert refused.status_code == 400 and refused.json()["detail"] == messages.API_DETAIL["no_reply_target"]
    assert (await _comment(world, ticket["id"], "note for us")).status_code == 200
    assert [c["text"] for c in (await _stored(world.db, ticket["id"]))["comments"]] == ["note for us"]


async def test_a_reply_where_the_requester_cannot_read_it_is_refused(world):
    """protects=D-11 a legacy tray ticket without My tickets, and a ticket with no requester channel;
    fails_when=either reply is stored."""
    ticket = await _raise(world)
    await world.db.tickets.update_one({"id": ticket["id"]}, {"$set": {
        "raised_via": "tray", "requester_channel": {"tray": True, "myTickets": False}}})
    refused = await _comment(world, ticket["id"], REPLY, visibility="requester")
    assert refused.status_code == 400 and refused.json()["detail"] == messages.API_DETAIL["no_reply_target"]
    await world.db.tickets.update_one({"id": ticket["id"]}, {"$set": {
        "raised_via": "portal", "requester_channel": None}})
    assert (await _comment(world, ticket["id"], REPLY, visibility="requester")).status_code == 400
    await world.db.tickets.update_one({"id": ticket["id"]}, {"$set": {
        "requester_channel": {"tray": True, "myTickets": True}, "raised_via": "tray"}})
    assert (await _comment(world, ticket["id"], REPLY, visibility="requester")).status_code == 200
    assert [c["text"] for c in (await _stored(world.db, ticket["id"]))["comments"]] == [REPLY]


async def test_a_requester_reply_on_a_missing_or_foreign_ticket_is_not_found(world):
    """protects=the visibility check reads inside the caller's tenant; fails_when=another tenant's ticket
    answers anything but 404."""
    ticket = await _raise(world)
    foreign = await _comment(world, ticket["id"], REPLY, user=portal_user("t2", "dave@y.co"), visibility="requester")
    assert foreign.status_code == 404
    assert (await _comment(world, "no-such-ticket", REPLY, visibility="requester")).status_code == 404
    assert (await _stored(world.db, ticket["id"]))["comments"] == []


async def test_history_keeps_a_preview_only_for_requester_comments(world):
    """protects=D-11 history; fails_when=a staff-only comment's text is anywhere in the ticket history."""
    ticket = await _raise(world)
    await _comment(world, ticket["id"], SECRET)
    await _comment(world, ticket["id"], REPLY + " " + "y" * 100, visibility="requester")
    await _drain()
    entries = [h for h in (await _stored(world.db, ticket["id"]))["history"] if h["action"] == "commented"]
    assert len(entries) == 2
    assert "preview" not in entries[0]["changes"] and entries[0]["changes"] == {}
    assert entries[1]["changes"]["preview"] == (REPLY + " " + "y" * 100)[:80]
    assert "hunter2" not in json.dumps(entries)


async def test_the_requester_projection_returns_requester_comments_only(world):
    """protects=PROH-85-05 projection; fails_when=a staff comment, or a comment with no visibility at all, is
    projected."""
    ticket = await _raise(world)
    await _comment(world, ticket["id"], SECRET)
    await _comment(world, ticket["id"], REPLY, visibility="requester")
    await world.db.tickets.update_one({"id": ticket["id"]}, {"$push": {"comments": {
        "id": "old", "author": "bob@x.co", "text": "written before the flag existed",
        "created_at": "2026-01-01T00:00:00+00:00", "edited": False}}})
    stored = await _stored(world.db, ticket["id"])
    assert [i["text"] for i in projection.requester_items(stored)] == [REPLY]
    view = await world.call("GET", f"/api/tickets/{ticket['id']}/service-desk", user=ALICE)
    assert view.status_code == 200
    assert "hunter2" not in view.text and "before the flag" not in view.text and REPLY in view.text


# ---------------------------------------------------------------- Task 2: notices and the reader

async def _spy_recipients(monkeypatch):
    import ticket_notifications
    sent = []
    original = ticket_notifications._send

    async def spy(*args, **kwargs):
        sent.append(kwargs)
        return await original(*args, **kwargs)

    monkeypatch.setattr(ticket_notifications, "_send", spy)
    return sent


async def _notices(db, event):
    return await db.notifications.find({"metadata.event": event}, {"_id": 0}).to_list(20)


async def test_a_staff_comment_notice_has_no_text_and_does_not_address_the_reporter(world, monkeypatch):
    """protects=T-85-26; fails_when=any part of the staff comment is in the notice, the reporter is a recipient,
    the notice is not tagged for ticket staff, or the staff notice goes out on the tenant-wide socket (WR-201)."""
    sent = await _spy_recipients(monkeypatch)
    ticket = await _raise(world)
    await world.db.tickets.update_one({"id": ticket["id"]}, {"$set": {"watchers": ["carol@x.co", "alice@x.co"]}})
    assert (await _comment(world, ticket["id"], SECRET)).status_code == 200
    await _drain()
    notices = await _notices(world.db, "ticket_comment_added")
    assert len(notices) == 1
    notice = notices[0]
    assert "hunter2" not in json.dumps(notice) and "admin password" not in json.dumps(notice)
    assert notice["metadata"]["audience"] == "ticket_staff" and "recipient" not in notice["metadata"]
    assert len(sent) == 1 and sent[0]["message"] == "New staff comment on ticket 'My laptop will not start'"
    assert "alice@x.co" not in sent[0]["recipients"] and "carol@x.co" in sent[0]["recipients"]
    comment_pushes = [p for p in world.pushed if p["metadata"].get("event") == "ticket_comment_added"]
    assert comment_pushes == [] and "hunter2" not in json.dumps(world.pushed)     # the socket reaches the reporter too
    assert "bob@x.co" not in json.dumps(world.pushed)


async def test_a_requester_comment_notice_keeps_the_preview_and_names_the_reporter(world, monkeypatch):
    """protects=D-33; fails_when=the preview is dropped, the recipient tag is missing or not lowercase, or the
    preview goes out on the tenant-wide socket."""
    sent = await _spy_recipients(monkeypatch)
    ticket = await _raise(world, user=portal_user("t1", "Alice@X.co"))
    assert (await _comment(world, ticket["id"], REPLY, visibility="requester")).status_code == 200
    await _drain()
    notices = await _notices(world.db, "ticket_comment_added")
    assert len(notices) == 1
    assert len(sent) == 1 and REPLY in sent[0]["message"]
    assert notices[0]["metadata"]["recipient"] == "alice@x.co" and "audience" not in notices[0]["metadata"]
    pushes = [p for p in world.pushed if p["metadata"].get("event") == "ticket_comment_added"]
    assert len(pushes) == 1 and pushes[0]["message"] == "" and REPLY not in json.dumps(world.pushed)


async def test_a_mention_notice_is_tagged_with_the_mentioned_address(world):
    """protects=D-33 mentions; fails_when=the mention notice has no recipient tag or keeps the original case."""
    ticket = await _raise(world)
    assert (await _comment(world, ticket["id"], "please look, @Carol@X.co")).status_code == 200
    await _drain()
    mentions = await _notices(world.db, "mention")
    assert len(mentions) == 1 and mentions[0]["metadata"]["recipient"] == "carol@x.co"


async def test_the_feed_serves_a_tagged_notice_only_to_its_recipient(world):
    """protects=T-85-27; fails_when=a user reads a notice tagged for someone else, an untagged notice (or one
    with a null tag, or no metadata) stops reaching the tenant, another tenant's notice leaks, or the
    tenant-admin audience filter stops applying."""
    await world.db.notifications.insert_many([
        {"alert_id": "mine", "tenantId": "t1", "sent_at": "2026-11-08T00:00:01", "metadata": {"recipient": "alice@x.co"}},
        {"alert_id": "open", "tenantId": "t1", "sent_at": "2026-11-08T00:00:02", "metadata": {"event": "x"}},
        {"alert_id": "null-tag", "tenantId": "t1", "sent_at": "2026-11-08T00:00:03", "metadata": {"recipient": None}},
        {"alert_id": "no-meta", "tenantId": "t1", "sent_at": "2026-11-08T00:00:04", "metadata": None},
        {"alert_id": "admins", "tenantId": "t1", "sent_at": "2026-11-08T00:00:05", "metadata": {"audience": "tenant_admins"}},
        {"alert_id": "other-tenant", "tenantId": "t2", "sent_at": "2026-11-08T00:00:06", "metadata": {"recipient": "alice@x.co"}},
    ])
    alice = [n["alert_id"] for n in await _feed(world.db, ALICE)]
    assert alice == ["no-meta", "null-tag", "open", "mine"]
    bob = [n["alert_id"] for n in await _feed(world.db, BOB)]
    assert bob == ["no-meta", "null-tag", "open"]
    admin = [n["alert_id"] for n in await _feed(world.db, BOB, perms=("view:dashboard", "manage:agents"))]
    assert admin == ["admins", "no-meta", "null-tag", "open"]
    foreign = [n["alert_id"] for n in await _feed(world.db, OTHER_ALICE, tenant="t2")]
    assert foreign == ["other-tenant"]


async def test_the_feed_matches_the_recipient_case_insensitively_and_by_email(world):
    """protects=D-33 casefold; fails_when=a mixed-case username, or a user known by email, misses its notice."""
    await world.db.notifications.insert_one(
        {"alert_id": "mine", "tenantId": "t1", "sent_at": "2026-11-08T00:00:01", "metadata": {"recipient": "alice@x.co"}})
    assert [n["alert_id"] for n in await _feed(world.db, TokenData(username="  ALICE@x.CO ", tenant_id="t1"))] == ["mine"]
    by_email = SimpleNamespace(username="alice", email="Alice@X.co", role="user", tenant_id="t1")
    assert [n["alert_id"] for n in await _feed(world.db, by_email)] == ["mine"]
    assert await _feed(world.db, TokenData(username="", tenant_id="t1")) == []


async def test_staff_only_text_reaches_neither_the_reporters_feed_nor_the_tenants(world):
    """protects=PROH-85-05 end to end; fails_when=the secret appears anywhere the reporter or another user
    reads, or the requester-visible reply fails to reach the reporter (and only the reporter)."""
    ticket = await _raise(world)
    assert (await _comment(world, ticket["id"], SECRET)).status_code == 200
    assert (await _comment(world, ticket["id"], REPLY, visibility="requester")).status_code == 200
    await _drain()
    alice = await _feed(world.db, ALICE)
    carol = await _feed(world.db, CAROL)
    bob = await _feed(world.db, BOB)
    everything = json.dumps([alice, carol, bob, world.pushed])
    assert "hunter2" not in everything and REPLY not in everything
    reply_notice = lambda feed: [n for n in feed if n["metadata"].get("recipient")]   # noqa: E731
    assert len(reply_notice(alice)) == 1 and reply_notice(alice)[0]["metadata"]["recipient"] == "alice@x.co"
    assert reply_notice(carol) == [] and reply_notice(bob) == []       # the technician wrote it; the notice is the reporter's
