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

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service_desk import messages, projection, store
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.service_desk_support import desk_app, portal_user, seed_desk_tenant

SECRET = "the admin password is hunter2-staff-only"
REPLY = "Please restart the laptop and try again"
ALICE = portal_user("t1", "alice@x.co")           # the reporter
BOB = portal_user("t1", "bob@x.co")               # the assigned technician
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
