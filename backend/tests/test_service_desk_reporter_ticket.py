"""The reporter's own ticket on the legacy ticket routes (Phase 85, plan 85-25, CR-401 server half). Real MongoDB
(skips without one) through the throwaway database of tests/_mongo_test_db.py.

Value: protects=CR-401 / D-11 / PROH-85-05 / PROH-85-13 / T-85-90: the person who raised a ticket never
receives a staff-only comment, an unsent AI draft, the text of a withdrawn answer, a desk field or a history
entry about a comment they cannot read, on any route of tickets_endpoints.py that returns the ticket, while
a technician who did not raise it still gets the stored ticket and another tenant gets 404; fails_when=a
planted staff text, draft text, withdrawn text, desk reason or draft history entry reaches the reporter on a
route, the reporter's own comment or a requester-visible one goes missing, staff lose any of it, the
shared case table and projection.requester_may_read disagree, or a route that returns a ticket skips the
projection; no_claim=the UI filter (85-26) and the desk routes.
"""
import ast
import json
import os
import pathlib
import sys
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service_desk import projection, store
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.service_desk_support import desk_app, portal_user, seed_desk_tenant

CASES = json.loads((pathlib.Path(__file__).resolve().parents[2] / "shared" / "service-desk-requester-comments.json")
                   .read_text(encoding="utf-8"))
ALICE = portal_user("t1", "alice@x.co")           # the reporter
BOB = portal_user("t1", "bob@x.co")               # a technician who did not raise the ticket
ALICE_ADMIN = portal_user("t1", "alice@x.co", role="admin")
OTHER_ALICE = portal_user("t2", "alice@x.co")

STAFF_TEXT = "the admin password is hunter2-staff-only"
OLD_STAFF = "written before the flag existed, staff eyes only"
DRAFT = "unsent draft about the refund policy"
WITHDRAWN = "an answer that was taken back"
NOTE = "Staff reason: refund request needs a person"
REPLY = "Please restart the laptop and try again"
OWN = "It still shows a black screen"
OWN_REPLY = "I still need help with this"
ANSWER = "Hold the power button for ten seconds"
WNOTICE = "This answer was withdrawn; a person will follow up."
HNOTICE = "A person from IT will pick this up"
HIDDEN = [STAFF_TEXT, OLD_STAFF, DRAFT, WITHDRAWN, NOTE, "billing_topic", "mode_drafts", "contentHash", "actionId",
          "AO-x", "draft_sent", "draft_discarded"]
SHOWN = [REPLY, OWN, OWN_REPLY, ANSWER, WNOTICE, HNOTICE]
AT = "2026-11-01T10:00:0{}+00:00"


def _comment(cid, author, text, visibility, n, **extra):
    return {"id": cid, "author": author, "text": text, "created_at": AT.format(n), "edited": False,
            "visibility": visibility, **extra}


def _planted_comments():
    old = _comment("c-old", "bob@x.co", OLD_STAFF, None, 2)
    del old["visibility"]                                           # written before the flag existed
    return [
        _comment("c-staff", "bob@x.co", STAFF_TEXT, "staff", 1),
        old,
        _comment("c-reply", "bob@x.co", REPLY, "requester", 3),
        _comment("c-own", "Alice@X.co", OWN, "staff", 4),           # the portal default, the author in another case
        _comment("c-own-reply", "alice@x.co", OWN_REPLY, "requester", 5, kind="requester_reply"),
        _comment("c-draft", "desk", DRAFT, "staff", 6, kind="ai_draft",
                 ai={"state": "draft", "actionId": "AO-x", "contentHash": "h1", "citations": []}),
        _comment("c-answer", "desk", ANSWER, "requester", 7, kind="ai_answer",
                 ai={"state": "posted", "actionId": "AO-x", "contentHash": "h2", "sentBy": "bob@x.co",
                     "postedAt": AT.format(7), "citations": [{"articleId": "kb-1", "title": "Power problems",
                                                              "excerpt": "internal excerpt", "contentHash": "h3"}]}),
        _comment("c-withdrawn", "desk", WITHDRAWN, "requester", 8, kind="ai_answer",
                 ai={"state": "withdrawn", "actionId": "AO-x", "withdrawnAt": AT.format(8)}),
        _comment("c-wnotice", "desk", WNOTICE, "requester", 9, kind="withdrawn_notice"),
        _comment("c-hnotice", "desk", HNOTICE, "requester", 9, kind="handoff_notice"),
        _comment("c-note", "desk", NOTE, "staff", 9, kind="staff_note"),
    ]


def _entry(n, actor, action, changes):
    return {"id": f"h{n}", "actor": actor, "action": action, "changes": changes, "created_at": AT.format(n)}


def _planted_history():
    return [
        _entry(0, "alice@x.co", "created", {"status": "open"}),
        _entry(1, "bob@x.co", "commented", {}),                                           # staff-only, no preview
        _entry(2, "bob@x.co", "commented", {"preview": REPLY[:80]}),                       # a requester reply
        _entry(3, "desk", "commented", {"kind": "ai_draft", "visibility": "staff"}),
        _entry(4, "desk", "commented", {"kind": "staff_note", "visibility": "staff"}),
        _entry(5, "desk", "commented", {"kind": "ai_answer", "visibility": "requester"}),
        _entry(6, "alice@x.co", "commented", {}),                                          # the reporter's own
        _entry(7, "bob@x.co", "commented", {"preview": STAFF_TEXT[:80]}),                  # an older preview, now staff-only
        _entry(8, "desk", "draft_sent", {"comment": "c-draft"}),
        _entry(9, "desk", "draft_discarded", {"comment": "c-draft"}),
        _entry(9, "bob@x.co", "updated", {"status": "in_progress"}),
    ]


KEPT_IDS = ["h0", "h2", "h5", "h6", "h9"]          # created, a requester reply, the desk answer, the reporter's own, the status change


@pytest.fixture
async def world(mongo_db, monkeypatch):  # noqa: F811
    await store.ensure_indexes(mongo_db)
    await seed_desk_tenant(mongo_db, "t1")
    await seed_desk_tenant(mongo_db, "t2")
    import ticket_notifications
    monkeypatch.setattr(ticket_notifications, "notify_comment_added", AsyncMock())
    import service_desk.intake as intake
    monkeypatch.setattr(intake, "on_ticket_created", AsyncMock())       # the desk's own intake is not under test here
    return desk_app(mongo_db, monkeypatch)


async def _raise(world, user, title="My laptop will not start"):
    response = await world.call("POST", "/api/tickets", user=user, json={"title": title, "description": "black screen"})
    assert response.status_code == 200, response.text
    return response.json()


async def _plant(world):
    """Alice's ticket carrying one comment of every kind, desk state and history; plus bob's plain ticket."""
    ticket = await _raise(world, ALICE)
    desk = {"phase": "handed_off", "lastReason": "billing_topic", "draftReason": "mode_drafts",
            "draftWaiting": True, "actionId": "AO-x", "commentId": "c-draft"}
    await world.db.tickets.update_one({"id": ticket["id"]}, {"$set": {
        "comments": _planted_comments(), "desk": desk, "history": _planted_history()}})
    other = await _raise(world, BOB, title="Bob's own ticket")
    return ticket["id"], other["id"]


async def _stored(world, ticket_id):
    return await world.db.tickets.find_one({"id": ticket_id}, {"_id": 0})


def _clean(text):
    """The planted staff texts are absent and the readable ones are present."""
    for secret in HIDDEN:
        assert secret not in text, secret
    for shown in SHOWN:
        assert shown in text, shown


# ---------------------------------------------------------------- the case table (pure)

def test_the_case_table_agrees_with_the_server_rule():
    """protects=the single source of what the reporter may read; fails_when=requester_may_read and the shared
    table (which the UI helper is tested against too) disagree on a case."""
    assert len(CASES["cases"]) >= 14
    ticket = {"reporter": CASES["reporter"]}
    for case in CASES["cases"]:
        assert projection.requester_may_read(ticket, case["comment"]) is case["readable"], case["id"]


def test_the_reporter_projection_keeps_only_the_named_ai_keys():
    """protects=T-85-90; fails_when=an AI comment keeps a field outside REPORTER_AI_KEYS or a citation keeps more
    than the article id and title."""
    assert projection.REPORTER_DESK_KEYS == ()
    ticket = {"reporter": "alice@x.co", "desk": {"phase": "posted"}, "comments": _planted_comments()}
    shown = projection.reporter_ticket(ticket)
    answer = next(c for c in shown["comments"] if c["id"] == "c-answer")
    assert set(answer["ai"]) <= set(projection.REPORTER_AI_KEYS)
    assert answer["ai"]["citations"] == [{"articleId": "kb-1", "title": "Power problems"}]
    assert "desk" not in shown and "history" not in shown
    assert [c["id"] for c in shown["comments"]] == ["c-reply", "c-own", "c-own-reply", "c-answer", "c-wnotice", "c-hnotice"]
    assert ticket["comments"][5]["ai"]["actionId"] == "AO-x"                    # the stored ticket is not touched


def test_the_panel_and_the_comment_list_share_one_visibility_rule():
    """protects=the drift guard; fails_when=requester_items and requester_may_read stop sharing _requester_visible."""
    ticket = {"reporter": "alice@x.co", "comments": _planted_comments()}
    assert sorted(i["id"] for i in projection.requester_items(ticket)) == sorted(
        c["id"] for c in ticket["comments"] if projection._requester_visible(c))


# ---------------------------------------------------------------- GET /api/tickets/{id}

async def test_the_reporter_reads_their_own_ticket_without_the_staff_side(world):
    """protects=CR-401 / PROH-85-13 on GET; fails_when=any planted staff text, draft, withdrawn text, desk field
    or draft history entry is in the reporter's response, or a comment they may read is missing."""
    ticket_id, _ = await _plant(world)
    response = await world.call("GET", f"/api/tickets/{ticket_id}", user=ALICE)
    assert response.status_code == 200
    _clean(response.text)
    body = response.json()
    assert "desk" not in body
    assert [c["id"] for c in body["comments"]] == ["c-reply", "c-own", "c-own-reply", "c-answer", "c-wnotice", "c-hnotice"]
    assert [h["id"] for h in body["history"]] == KEPT_IDS
    assert body["title"] == "My laptop will not start" and body["reporter"] == "alice@x.co"


async def test_a_technician_who_did_not_raise_the_ticket_gets_it_unchanged(world):
    """protects=D-11 for staff; fails_when=the stored comments, desk or history differ for a non-reporter."""
    ticket_id, _ = await _plant(world)
    stored = await _stored(world, ticket_id)
    response = await world.call("GET", f"/api/tickets/{ticket_id}", user=BOB)
    assert response.status_code == 200
    body = response.json()
    assert body["comments"] == stored["comments"] and body["desk"] == stored["desk"] and body["history"] == stored["history"]


async def test_another_tenant_gets_404(world):
    """protects=tenant isolation; fails_when=a user of tenant t2 can read the ticket."""
    ticket_id, _ = await _plant(world)
    assert (await world.call("GET", f"/api/tickets/{ticket_id}", user=OTHER_ALICE)).status_code == 404


async def test_a_reporter_with_an_admin_role_still_gets_the_requester_view(world):
    """protects=A-85-G06 (T-85-93); fails_when=the reporter's role decides the projection instead of who raised it."""
    ticket_id, _ = await _plant(world)
    response = await world.call("GET", f"/api/tickets/{ticket_id}", user=ALICE_ADMIN)
    assert response.status_code == 200
    _clean(response.text)


# ---------------------------------------------------------------- every other ticket-returning route

BOB_NOTE = "bob's own private note on his own ticket"


async def _bob_note(world, other_id):
    await world.db.tickets.update_one({"id": other_id}, {"$set": {"comments": [
        _comment("b1", "carol@x.co", BOB_NOTE, "staff", 1)]}})


@pytest.mark.parametrize("query", ["", "?reporter=alice@x.co"])
async def test_the_list_projects_the_reporters_ticket_and_leaves_the_others(world, query):
    """protects=CR-401 on GET /api/tickets; fails_when=a planted staff text reaches the reporter in the list, or
    a ticket raised by someone else loses a comment."""
    ticket_id, other_id = await _plant(world)
    await _bob_note(world, other_id)
    response = await world.call("GET", f"/api/tickets{query}", user=ALICE)
    assert response.status_code == 200
    tickets = {t["id"]: t for t in response.json()["tickets"]}
    assert ticket_id in tickets
    _clean(json.dumps(tickets[ticket_id]))
    assert "desk" not in tickets[ticket_id]
    if not query:
        assert [c["text"] for c in tickets[other_id]["comments"]] == [BOB_NOTE]
    staff = await world.call("GET", "/api/tickets", user=BOB)
    mine = next(t for t in staff.json()["tickets"] if t["id"] == ticket_id)
    assert mine["desk"]["lastReason"] == "billing_topic" and len(mine["comments"]) == len(_planted_comments())


async def test_patch_returns_the_projection_to_the_reporter_and_the_full_ticket_to_staff(world):
    """protects=CR-401 on PATCH; fails_when=the reporter's update response carries a staff text, or staff lose it."""
    ticket_id, _ = await _plant(world)
    response = await world.call("PATCH", f"/api/tickets/{ticket_id}", user=ALICE, json={"priority": "high"})
    assert response.status_code == 200 and response.json()["priority"] == "high"
    _clean(response.text)
    staff = await world.call("PATCH", f"/api/tickets/{ticket_id}", user=BOB, json={"priority": "low"})
    assert staff.status_code == 200 and STAFF_TEXT in staff.text and staff.json()["desk"]["lastReason"] == "billing_topic"


async def test_a_comment_by_the_reporter_comes_back_in_the_projection(world):
    """protects=CR-401 / A-85-G05 on POST comments; fails_when=the reporter's new comment is missing from the
    response (a portal comment is stored staff-only) or a staff text is in it."""
    ticket_id, _ = await _plant(world)
    response = await world.call("POST", f"/api/tickets/{ticket_id}/comments", user=ALICE, json={"text": "One more thing"})
    assert response.status_code == 200
    _clean(response.text)
    assert "One more thing" in [c["text"] for c in response.json()["comments"]]
    staff = await world.call("POST", f"/api/tickets/{ticket_id}/comments", user=BOB, json={"text": "Checking now"})
    assert staff.status_code == 200 and STAFF_TEXT in staff.text and "desk" in staff.json()


async def test_the_link_routes_project_for_the_reporter(world):
    """protects=CR-401 on POST links and DELETE links; fails_when=either response carries a staff text or a desk key."""
    ticket_id, other_id = await _plant(world)
    linked = await world.call("POST", f"/api/tickets/{ticket_id}/links", user=ALICE,
                              json={"linked_id": other_id, "link_type": "relates_to"})
    assert linked.status_code == 200 and linked.json()["links"][0]["linked_id"] == other_id
    _clean(linked.text)
    removed = await world.call("DELETE", f"/api/tickets/{ticket_id}/links/{other_id}", user=ALICE)
    assert removed.status_code == 200 and removed.json()["links"] == []
    _clean(removed.text)
    staff = await world.call("POST", f"/api/tickets/{ticket_id}/links", user=BOB,
                             json={"linked_id": other_id, "link_type": "relates_to"})
    assert staff.status_code == 200 and STAFF_TEXT in staff.text


async def test_the_work_log_route_projects_for_the_reporter(world):
    """protects=CR-401 on POST work-log; fails_when=the response carries a staff text or a desk key."""
    ticket_id, _ = await _plant(world)
    response = await world.call("POST", f"/api/tickets/{ticket_id}/work-log", user=ALICE,
                                json={"hours": 1, "description": "checked"})
    assert response.status_code == 200 and response.json()["work_logs"][0]["description"] == "checked"
    _clean(response.text)


@pytest.mark.parametrize("method,path,body", [
    ("approve_ticket", "approve", {}), ("reject_ticket", "reject", {"reason": "no"}),
    ("escalate_ticket", "escalate", {"reason": "slow"})])
async def test_approve_reject_and_escalate_project_whatever_the_service_returns(world, monkeypatch, method, path, body):
    """protects=CR-401 on the approval routes; fails_when=the route returns the service's full ticket to the
    reporter, or changes it for staff."""
    ticket_id, _ = await _plant(world)
    full = await _stored(world, ticket_id)
    import tickets_service
    monkeypatch.setattr(tickets_service.tickets_service, method, AsyncMock(return_value=full))
    response = await world.call("POST", f"/api/tickets/{ticket_id}/{path}", user=ALICE, json=body)
    assert response.status_code == 200
    _clean(response.text)
    staff = await world.call("POST", f"/api/tickets/{ticket_id}/{path}", user=BOB, json=body)
    assert staff.json()["comments"] == full["comments"] and staff.json()["desk"] == full["desk"]


async def test_a_new_ticket_goes_back_to_its_creator_through_the_projection(world, monkeypatch):
    """protects=CR-401 on POST /api/tickets; fails_when=the creator's response carries a desk key or a staff text."""
    ticket_id, _ = await _plant(world)
    full = await _stored(world, ticket_id)
    import tickets_service
    monkeypatch.setattr(tickets_service.tickets_service, "create_ticket", AsyncMock(return_value=full))
    response = await world.call("POST", "/api/tickets", user=ALICE, json={"title": "Another one"})
    assert response.status_code == 200
    _clean(response.text)
    assert "desk" not in response.json()
    real = await _raise(world, ALICE, title="A plain new ticket")
    assert "desk" not in real and real["reporter"] == "alice@x.co"


# ---------------------------------------------------------------- history

async def test_the_history_route_drops_what_the_reporter_may_not_read(world):
    """protects=T-85-91 / A-85-G08; fails_when=a draft entry, a staff-only commented entry or an older preview of
    a now staff-only comment reaches the reporter, a status entry or one of theirs is lost, or staff lose an entry."""
    ticket_id, _ = await _plant(world)
    response = await world.call("GET", f"/api/tickets/{ticket_id}/history", user=ALICE)
    assert response.status_code == 200
    assert sorted(h["id"] for h in response.json()) == sorted(KEPT_IDS)
    for secret in (STAFF_TEXT, "draft_sent", "draft_discarded", "ai_draft", "staff_note"):
        assert secret not in response.text
    stored = await _stored(world, ticket_id)
    staff = await world.call("GET", f"/api/tickets/{ticket_id}/history", user=BOB)
    assert staff.json() == sorted(stored["history"], key=lambda h: h["created_at"], reverse=True)
    assert (await world.call("GET", f"/api/tickets/{ticket_id}/history", user=OTHER_ALICE)).status_code == 404


# ---------------------------------------------------------------- the route check

_PROJECTED = ("get_ticket", "list_tickets", "create_ticket", "update_ticket", "get_history", "add_comment", "add_link",
              "remove_link", "log_work", "approve_ticket", "reject_ticket", "escalate_ticket")
_TICKET_NAMES = ("ticket", "updated", "history", "result")


def _routes():
    tree = ast.parse((pathlib.Path(__file__).resolve().parents[1] / "tickets_endpoints.py").read_text(encoding="utf-8"))
    return [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and any(
        isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and isinstance(d.func.value, ast.Name)
        and d.func.value.id == "router" for d in n.decorator_list)]


def _calls(fn):
    return {c.func.id for c in ast.walk(fn) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}


def test_every_route_that_returns_a_ticket_goes_through_the_projection():
    """protects=T-85-92; fails_when=a route returns a ticket, updated, history or result value without _shown or
    _shown_history, or one of the twelve named routes stops calling them."""
    routes = {fn.name: fn for fn in _routes()}
    for name in _PROJECTED:
        assert name in routes, name
        assert _calls(routes[name]) & {"_shown", "_shown_history"}, f"{name} skips the reporter projection"
    for name, fn in routes.items():
        for node in ast.walk(fn):
            if isinstance(node, ast.Return) and isinstance(node.value, ast.Name) and node.value.id in _TICKET_NAMES:
                # the list returns its result dict, whose tickets were projected one by one (checked above)
                assert name == "list_tickets", f"{name} returns {node.value.id} unprojected"
