"""The portal service desk routes (Phase 85, plan 85-14, DESK-01, decisions D-07 to D-10, D-14). Real MongoDB
(skips without one) through the throwaway database of tests/_mongo_test_db.py; the local model is a stand-in.

Value: protects=staff send, edit or discard a draft through the HTTP routes with the plain-words refusals, the
reporter never sees or acts on a draft, another tenant never learns a ticket exists, and the requester view
never contains a draft, a staff note or a reason; fails_when=the reporter can send their own draft, a draft
or its existence reaches the reporter, a refusal returns a different code or text than the table, or a foreign
tenant gets anything but 404; no_claim=the lifecycle edge cases (test_service_desk_lifecycle.py).
"""
import asyncio
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service_desk import messages
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.service_desk_portal_support import (ANSWER, DAVE, DRAFT_ALICE, STAFF2, STAFF3, build_world, desk_row,
                                               draft_of, notices, raise_and_run, stored)

SECRET = "internal-only: the admin password is hunter2"


@pytest.fixture
async def world(mongo_db, monkeypatch):  # noqa: F811
    return await build_world(mongo_db, monkeypatch)


def _path(ticket, tail=""):
    return f"/api/tickets/{ticket['id']}/service-desk{tail}"


async def _draft(world):
    ticket = await raise_and_run(world, DRAFT_ALICE)
    return ticket, draft_of(ticket)


# ---------------------------------------------------------------- the view

async def test_staff_see_the_waiting_draft_and_the_reporter_does_not(world):
    """protects=D-09 / T-85-52 the draft panel data for staff, nothing for the reporter; fails_when=the reporter's
    response carries the draft text, its id or the flag."""
    ticket, comment = await _draft(world)
    staff = (await world.call("GET", _path(ticket), user=STAFF2)).json()
    draft = staff["draft"]
    assert staff["isRequester"] is False and staff["requester"] is None and staff["draftWaiting"] is True
    assert staff["canReplyToRequester"] is True
    assert draft["commentId"] == comment["id"] and draft["answer"] == ANSWER and draft["maxAnswerLength"] == 900
    assert draft["actionId"] == comment["ai"]["actionId"] and draft["articleCount"] == 1
    assert draft["citations"] == [{"articleId": "kb-pw", "title": "Reset your own password"}]
    assert draft["draftReason"] == "mode_drafts" and draft["draftReasonText"] == messages.DRAFT_REASON_TEXT["mode_drafts"]
    assert draft["canActOnDraft"] is True and draft["blockedReason"] is None and draft["blockedText"] is None
    assert draft["reporter"] == "alice@x.co" and draft["createdAt"]

    mine = await world.call("GET", _path(ticket), user=DRAFT_ALICE)
    body = mine.json()
    assert body["isRequester"] is True and body["draft"] is None and body["draftWaiting"] is False
    assert body["canReplyToRequester"] is False
    assert ANSWER not in mine.text and comment["id"] not in mine.text and body["requester"]["items"] == []


async def test_a_blocked_draft_says_why_in_the_panel_data(world):
    """protects=D-09 blockedReason and blockedText for each cause; fails_when=canActOnDraft stays true or the
    text differs from the table."""
    ticket, comment = await _draft(world)
    await world.db.tickets.update_one({"id": ticket["id"]}, {"$set": {"status": "resolved"}})
    draft = (await world.call("GET", _path(ticket), user=STAFF2)).json()["draft"]
    assert draft["canActOnDraft"] is False and draft["blockedReason"] == "ticket_closed"
    assert draft["blockedText"] == messages.API_DETAIL["ticket_closed"].format(state="resolved")

    await world.db.tickets.update_one({"id": ticket["id"]}, {"$set": {"status": "open", "desk.personReplied": True}})
    draft = (await world.call("GET", _path(ticket), user=STAFF2)).json()["draft"]
    assert draft["blockedReason"] == "person_replied" and draft["blockedText"] == messages.API_DETAIL["person_replied"]

    await world.db.tickets.update_one({"id": ticket["id"]}, {"$set": {"desk.personReplied": False, "requester_channel": {
        "portal": False, "tray": True, "myTickets": False}}})
    view = (await world.call("GET", _path(ticket), user=STAFF2)).json()
    assert view["draft"]["blockedReason"] == "no_requester" and view["canReplyToRequester"] is False


async def test_another_tenant_gets_404_on_every_route(world):
    """protects=T-85-52 tenant isolation; fails_when=a user of another tenant reads or changes the ticket."""
    ticket, comment = await _draft(world)
    cid = comment["id"]
    for method, tail, body in (("GET", "", None), ("POST", f"/drafts/{cid}/send", None),
                               ("POST", f"/drafts/{cid}/edit", {"text": "new"}), ("POST", f"/drafts/{cid}/discard", None)):
        response = await world.call(method, _path(ticket, tail), user=DAVE, json=body)
        assert response.status_code == 404, (tail, response.text)
    assert draft_of(await stored(world.db, ticket["id"]))["ai"]["state"] == "draft"


# ---------------------------------------------------------------- send, edit, discard

async def test_staff_send_a_draft_and_the_requester_reads_it(world):
    """protects=D-09 the full path through HTTP: 200, the answer is requester-visible with the AI-assisted
    kind and its citations, the requester view lists it, the ticket waits on the customer;
    fails_when=any step is missing."""
    ticket, comment = await _draft(world)
    response = await world.call("POST", _path(ticket, f"/drafts/{comment['id']}/send"), user=STAFF2)
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "sent", "commentId": comment["id"], "edited": False}

    mine = (await world.call("GET", _path(ticket), user=DRAFT_ALICE)).json()
    [item] = mine["requester"]["items"]
    assert item["kind"] == "ai_answer" and item["text"] == ANSWER and item["citations"][0]["articleId"] == "kb-pw"
    assert mine["status"] == "pending_customer" and mine["draft"] is None
    row = await desk_row(world.db, ticket, "t2")
    assert row["state"] == "executed" and re.fullmatch(r"Sent by Bob at \d\d:\d\d\. Waiting for the requester\.",
                                                        row["activityResult"])
    assert len(await notices(world.db, "alice@x.co", "answer_sent")) == 1


async def test_staff_edit_and_send_and_the_refusals_use_the_table_texts(world):
    """protects=D-09 the edit route and its 422 texts; fails_when=an empty, unchanged or over-long edit is
    accepted or says something else."""
    ticket, comment = await _draft(world)
    url = _path(ticket, f"/drafts/{comment['id']}/edit")
    for text, key in (("", "draft_empty"), (ANSWER, "edit_unchanged"), ("z" * 901, "draft_too_long")):
        response = await world.call("POST", url, user=STAFF2, json={"text": text})
        assert response.status_code == 422, (key, response.text)
        assert response.json()["detail"] == messages.API_DETAIL[key].format(max=900)
    assert draft_of(await stored(world.db, ticket["id"]))["ai"]["state"] == "draft"

    response = await world.call("POST", url, user=STAFF2, json={"text": "Choose Forgot password on the sign-in page."})
    assert response.status_code == 200 and response.json()["edited"] is True
    sent = draft_of(await stored(world.db, ticket["id"]))
    assert sent["text"] == "Choose Forgot password on the sign-in page." and sent["ai"]["edited"] is True
    assert (await world.call("POST", url, user=STAFF2, json={})).status_code == 422          # a body is required


async def test_staff_discard_a_draft_and_the_requester_never_sees_it(world):
    """protects=D-04 / D-10 discard through HTTP; fails_when=the requester view lists the draft or the status
    moves."""
    ticket, comment = await _draft(world)
    response = await world.call("POST", _path(ticket, f"/drafts/{comment['id']}/discard"), user=STAFF2)
    assert response.status_code == 200 and response.json()["status"] == "discarded"
    mine = await world.call("GET", _path(ticket), user=DRAFT_ALICE)
    assert mine.json()["requester"]["items"] == [] and ANSWER not in mine.text
    assert (await stored(world.db, ticket["id"]))["status"] == "open"
    staff = (await world.call("GET", _path(ticket), user=STAFF2)).json()
    assert staff["draft"] is None and staff["draftWaiting"] is False


async def test_the_reporter_cannot_send_edit_or_discard_their_own_draft(world):
    """protects=T-85-52 elevation: the reporter is refused 403 with the staff_only text on all three routes;
    fails_when=any of them succeeds or changes the draft."""
    ticket, comment = await _draft(world)
    cid = comment["id"]
    for tail, body in ((f"/drafts/{cid}/send", None), (f"/drafts/{cid}/edit", {"text": "I decide"}),
                       (f"/drafts/{cid}/discard", None)):
        response = await world.call("POST", _path(ticket, tail), user=DRAFT_ALICE, json=body)
        assert response.status_code == 403 and response.json()["detail"] == messages.API_DETAIL["staff_only"]
    after = await stored(world.db, ticket["id"])
    assert draft_of(after)["ai"]["state"] == "draft" and after["status"] == "open"


async def test_a_resolved_ticket_refuses_the_send_with_the_table_text_and_allows_the_discard(world):
    """protects=D-09 409 ticket_closed; fails_when=another code or text, or the discard is refused."""
    ticket, comment = await _draft(world)
    await world.db.tickets.update_one({"id": ticket["id"]}, {"$set": {"status": "closed"}})
    refused = await world.call("POST", _path(ticket, f"/drafts/{comment['id']}/send"), user=STAFF2)
    assert refused.status_code == 409
    assert refused.json()["detail"] == "This ticket is closed, so the draft can't be sent. You can still discard it."
    ok = await world.call("POST", _path(ticket, f"/drafts/{comment['id']}/discard"), user=STAFF2)
    assert ok.status_code == 200


async def test_a_reply_to_the_requester_blocks_the_draft(world):
    """protects=D-09 person_replied through the real comment route; fails_when=the draft is sent after staff
    replied to the requester, or a staff-only note blocks it."""
    ticket, comment = await _draft(world)
    note = await world.call("POST", f"/api/tickets/{ticket['id']}/comments", user=STAFF2,
                             json={"text": SECRET})
    assert note.status_code == 200
    ok = await world.call("POST", _path(ticket, f"/drafts/{comment['id']}/edit"), user=STAFF2, json={"text": "A change."})
    assert ok.status_code == 200

    other, comment2 = await _draft(world)
    reply = await world.call("POST", f"/api/tickets/{other['id']}/comments", user=STAFF2,
                             json={"text": "I am looking at it", "visibility": "requester"})
    assert reply.status_code == 200
    refused = await world.call("POST", _path(other, f"/drafts/{comment2['id']}/send"), user=STAFF2)
    assert refused.status_code == 409 and refused.json()["detail"] == messages.API_DETAIL["person_replied"]


async def test_a_tray_ticket_without_my_tickets_refuses_the_send(world):
    """protects=D-09 no_requester; fails_when=the send succeeds."""
    ticket, comment = await _draft(world)
    await world.db.tickets.update_one({"id": ticket["id"]}, {"$set": {"requester_channel": {
        "portal": False, "tray": True, "myTickets": False}}})
    refused = await world.call("POST", _path(ticket, f"/drafts/{comment['id']}/send"), user=STAFF2)
    assert refused.status_code == 409 and refused.json()["detail"] == messages.API_DETAIL["no_requester"]


async def test_two_sends_at_once_through_http_give_one_200_and_one_409(world):
    """protects=T-85-53; fails_when=both are 200 or both are 409."""
    ticket, comment = await _draft(world)
    url = _path(ticket, f"/drafts/{comment['id']}/send")
    first, second = await asyncio.gather(world.call("POST", url, user=STAFF2), world.call("POST", url, user=STAFF2))
    codes = sorted([first.status_code, second.status_code])
    assert codes == [200, 409]
    loser = first if first.status_code == 409 else second
    assert loser.json()["detail"] == messages.API_DETAIL["already_handled"]


async def test_an_unknown_draft_id_is_a_conflict_not_a_server_error(world):
    """protects=the routes answer a missing comment in plain words; fails_when=a 500."""
    ticket, _ = await _draft(world)
    response = await world.call("POST", _path(ticket, "/drafts/nope/send"), user=STAFF2)
    assert response.status_code == 409 and response.json()["detail"] == messages.API_DETAIL["already_handled"]
    assert (await world.call("POST", "/api/tickets/missing/service-desk/drafts/x/send", user=STAFF2)).status_code == 404


async def test_the_requester_view_holds_no_staff_text_or_reason(world):
    """protects=T-85-06 the requester block never contains a draft, a staff note or a reason; fails_when=the
    reporter's response holds any of them."""
    ticket, comment = await _draft(world)
    await world.call("POST", f"/api/tickets/{ticket['id']}/comments", user=STAFF3,
                           json={"text": SECRET})
    mine = await world.call("GET", _path(ticket), user=DRAFT_ALICE)
    for word in (SECRET, ANSWER, "Kept as a draft", "mode_drafts", "draftReason", "hunter2"):
        assert word not in mine.text
