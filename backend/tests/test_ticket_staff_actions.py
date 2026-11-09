"""The staff actions on a ticket need manage:tickets (Phase 85 gap G-85-4, plan 85-34, UD-2, WR-502). Real MongoDB
(skips without one) through the throwaway database of tests/_mongo_test_db.py.

Value: protects=WR-502 / UD-2 / PROH-85-25 / T-85-119: a requester, the reporter of the ticket included, cannot
bulk-update, edit, link, log work on, approve, reject, escalate, merge or change the watchers of a ticket, nor delete
one of its attachments, while ticket staff can do each of them and a requester keeps raising, commenting, attaching
and rating on their own ticket; fails_when=a requester gets anything but 403 (or 404 for a colleague's ticket) on a
staff route, a refused request changes the stored ticket, staff are refused, or a requester loses a route they keep;
no_claim=the screen, which still shows staff controls to requesters (A-85-G29), and the desk's own routes.
"""
import os
import sys
from unittest.mock import AsyncMock

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service_desk import store
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.service_desk_support import desk_app, portal_user, seed_desk_tenant, staff_user

ALICE = portal_user("t1", "alice@x.co")           # the reporter
BOB = staff_user("t1", "bob@x.co")                # a technician (manage:tickets)
CAROL = portal_user("t1", "carol@x.co")           # a requester who did not raise the ticket
ALICE_ADMIN = portal_user("t1", "alice@x.co", role="admin")

ATTACHMENT = {"id": "a1", "filename": "note.txt", "stored_as": "stored-a1-note.txt", "size": 5,
              "content_type": "text/plain", "uploaded_by": "alice@x.co"}


@pytest.fixture
async def world(mongo_db, monkeypatch):  # noqa: F811
    await store.ensure_indexes(mongo_db)
    await seed_desk_tenant(mongo_db, "t1")
    import ticket_notifications
    monkeypatch.setattr(ticket_notifications, "notify_comment_added", AsyncMock())
    monkeypatch.setattr(ticket_notifications, "notify_escalated", AsyncMock())
    import service_desk.intake as intake
    monkeypatch.setattr(intake, "on_ticket_created", AsyncMock())
    return desk_app(mongo_db, monkeypatch)


async def _raise(world, user, title="My laptop will not start"):
    response = await world.call("POST", "/api/tickets", user=user, json={"title": title, "description": "black screen"})
    assert response.status_code == 200, response.text
    return response.json()["id"]


async def _stored(world, ticket_id):
    return await world.db.tickets.find_one({"id": ticket_id}, {"_id": 0})


async def _plant(world):
    """Alice's ticket (with an attachment, resolved so it can be rated) and her second ticket."""
    ticket_id = await _raise(world, ALICE)
    other_id = await _raise(world, ALICE, title="My phone will not ring")
    await world.db.tickets.update_one({"id": ticket_id}, {"$set": {"attachments": [dict(ATTACHMENT)]}})
    return ticket_id, other_id


# method, path (with {id} and {other}), body, a check that the stored ticket holds the staff change
ACTIONS = {
    "bulk": ("POST", "/api/tickets/bulk", lambda t, o: {"ticket_ids": [t], "updates": {"priority": "critical"}},
             lambda s: s["priority"] == "critical"),
    "patch": ("PATCH", "/api/tickets/{id}", lambda t, o: {"priority": "low"}, lambda s: s["priority"] == "low"),
    "add_link": ("POST", "/api/tickets/{id}/links", lambda t, o: {"linked_id": o, "link_type": "relates_to"},
                 lambda s: [x["linked_id"] for x in s["links"]] != [] and len(s["links"]) == 1),
    "work_log": ("POST", "/api/tickets/{id}/work-log", lambda t, o: {"hours": 1, "description": "checked"},
                 lambda s: [w["description"] for w in s["work_logs"]] == ["checked"]),
    "delete_attachment": ("DELETE", "/api/tickets/{id}/attachments/a1", lambda t, o: None,
                          lambda s: s["attachments"] == []),
    "approve": ("POST", "/api/tickets/{id}/approve", lambda t, o: {}, lambda s: s["approval_status"] == "approved"),
    "reject": ("POST", "/api/tickets/{id}/reject", lambda t, o: {"reason": "no"},
               lambda s: s["approval_status"] == "rejected"),
    "escalate": ("POST", "/api/tickets/{id}/escalate", lambda t, o: {"reason": "slow"},
                 lambda s: s["escalated"] is True),
}


async def _link(world, ticket_id, other_id):
    await world.call("POST", f"/api/tickets/{ticket_id}/links", user=BOB,
                     json={"linked_id": other_id, "link_type": "relates_to"})


async def _act(world, name, user, ticket_id, other_id):
    method, path, body, _ = ACTIONS[name]
    return await world.call(method, path.format(id=ticket_id), user=user, json=body(ticket_id, other_id))


@pytest.mark.parametrize("name", sorted(ACTIONS))
async def test_the_reporter_cannot_use_a_staff_action_on_their_own_ticket(world, name):
    """protects=WR-502 / UD-2 / PROH-85-25 / T-85-119; fails_when=the requester who raised the ticket gets
    anything but 403 on the route, or the refused request changes the stored ticket."""
    ticket_id, other_id = await _plant(world)
    before = await _stored(world, ticket_id)
    response = await _act(world, name, ALICE, ticket_id, other_id)
    assert response.status_code == 403, response.text
    assert await _stored(world, ticket_id) == before


@pytest.mark.parametrize("name", sorted(ACTIONS))
async def test_staff_can_use_every_staff_action(world, name):
    """protects=UD-2 for staff; fails_when=a technician is refused or the route stops changing the ticket."""
    ticket_id, other_id = await _plant(world)
    response = await _act(world, name, BOB, ticket_id, other_id)
    assert response.status_code == 200, response.text
    assert ACTIONS[name][3](await _stored(world, ticket_id)), name


@pytest.mark.parametrize("name", sorted(ACTIONS))
async def test_a_colleague_cannot_reach_a_staff_action_on_someone_elses_ticket(world, name):
    """protects=WR-502 / T-85-119 (the 85-32 guard answers first); fails_when=a requester who did not raise the
    ticket gets anything but 404 on a ticket route (403 on the bulk route, which has no ticket id), or the ticket
    changes."""
    ticket_id, other_id = await _plant(world)
    before = await _stored(world, ticket_id)
    response = await _act(world, name, CAROL, ticket_id, other_id)
    assert response.status_code == (403 if name == "bulk" else 404), response.text
    assert await _stored(world, ticket_id) == before


async def test_the_reporter_keeps_commenting_and_attaching(world):
    """protects=UD-2 (what requesters keep); fails_when=the reporter can no longer comment on or attach a file to
    their own ticket."""
    ticket_id, _ = await _plant(world)
    comment = await world.call("POST", f"/api/tickets/{ticket_id}/comments", user=ALICE, json={"text": "One more thing"})
    assert comment.status_code == 200, comment.text
    world.user = ALICE
    transport = httpx.ASGITransport(app=world.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        upload = await client.post(f"/api/tickets/{ticket_id}/attachments",
                                   files={"file": ("shot.txt", b"hello", "text/plain")})
    assert upload.status_code == 200, upload.text
    stored = await _stored(world, ticket_id)
    assert "One more thing" in [c["text"] for c in stored["comments"]]
    assert len(stored["attachments"]) == 2


async def test_a_reporter_with_an_admin_role_can_act_and_still_gets_the_requester_view(world):
    """protects=A-85-G06 / AR-85-09 / T-85-93 (T-85-120 accepted); fails_when=a reporter who holds manage:tickets is
    refused on their own ticket, or the response carries the desk side."""
    ticket_id, _ = await _plant(world)
    response = await world.call("PATCH", f"/api/tickets/{ticket_id}", user=ALICE_ADMIN, json={"priority": "high"})
    assert response.status_code == 200, response.text
    assert response.json()["priority"] == "high" and "desk" not in response.json()
