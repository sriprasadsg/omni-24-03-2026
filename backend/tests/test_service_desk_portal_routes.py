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
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service_desk import messages
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.service_desk_support import portal_user
from tests.service_desk_portal_support import (ALICE, ANSWER, BOB, CAROL, DAVE, DRAFT_ALICE, STAFF2, STAFF3, build_world,
                                               desk_row, draft_of, notices, raise_and_run, stored)

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


# ---------------------------------------------------------------- Task 2: This fixed it, I still need help, comments

async def _posted(world):
    return await raise_and_run(world, ALICE)


async def test_the_reporter_confirms_and_the_view_says_so(world):
    """protects=D-07: 200, resolved with resolved_at, the requester view shows the confirmation and no buttons;
    fails_when=a colleague can confirm, or the view still offers the buttons."""
    ticket = await _posted(world)
    before = (await world.call("GET", _path(ticket), user=ALICE)).json()["requester"]
    assert before["canConfirm"] is True and before["notice"] is None and before["confirmedAt"] is None

    denied = await world.call("POST", _path(ticket, "/confirm"), user=BOB)
    assert denied.status_code == 403 and denied.json()["detail"] == messages.API_DETAIL["not_requester"]
    assert (await stored(world.db, ticket["id"]))["status"] == "pending_customer"

    response = await world.call("POST", _path(ticket, "/confirm"), user=ALICE)
    assert response.status_code == 200 and response.json() == {"status": "confirmed"}
    after = await stored(world.db, ticket["id"])
    assert after["status"] == "resolved" and after["resolved_at"] and after["desk"]["phase"] == "confirmed"
    view = (await world.call("GET", _path(ticket), user=ALICE)).json()
    assert view["status"] == "resolved" and view["requester"]["canConfirm"] is False
    assert view["requester"]["notice"] == "confirmed" and view["requester"]["confirmedAt"]
    again = await world.call("POST", _path(ticket, "/confirm"), user=ALICE)
    assert again.status_code == 409 and again.json()["detail"] == messages.API_DETAIL["not_confirmable"]


async def test_confirming_with_no_answer_waiting_is_a_conflict_and_a_stranger_gets_404(world):
    """protects=D-07 not_confirmable; fails_when=a draft-only ticket resolves or another tenant learns of it."""
    ticket, _ = await _draft(world)
    response = await world.call("POST", _path(ticket, "/confirm"), user=DRAFT_ALICE)
    assert response.status_code == 409 and response.json()["detail"] == messages.API_DETAIL["not_confirmable"]
    assert (await stored(world.db, ticket["id"]))["status"] == "open"
    for tail in ("/confirm", "/help"):
        assert (await world.call("POST", _path(ticket, tail), user=DAVE)).status_code == 404


async def test_i_still_need_help_by_the_reporter_goes_to_a_person(world):
    """protects=D-07 / D-31: 200 with the note stored, open, helped, one hand-off row; a colleague gets 403; the
    view then shows the helped notice; fails_when=a colleague can ask, or a second attempt starts."""
    ticket = await _posted(world)
    denied = await world.call("POST", _path(ticket, "/help"), user=BOB, json={"text": "me too"})
    assert denied.status_code == 403 and denied.json()["detail"] == messages.API_DETAIL["not_requester"]

    response = await world.call("POST", _path(ticket, "/help"), user=ALICE, json={"text": "still broken"})
    assert response.status_code == 200 and response.json() == {"status": "helped"}
    after = await stored(world.db, ticket["id"])
    assert after["status"] == "open" and after["desk"]["phase"] == "helped"
    [reply] = [c for c in after["comments"] if c.get("kind") == "requester_reply"]
    assert reply["visibility"] == "requester" and reply["author"] == "alice@x.co" and reply["text"] == "still broken"
    assert await world.db.service_desk_jobs.count_documents({}) == 1
    view = (await world.call("GET", _path(ticket), user=ALICE)).json()["requester"]
    assert view["notice"] == "helped" and view["canConfirm"] is False
    assert "still broken" in str(view["items"])


async def test_help_without_a_body_and_a_note_over_1000_characters(world):
    """protects=D-31 the body is optional, and 1001 characters is a 422 with the table text; fails_when=either
    differs."""
    ticket = await _posted(world)
    long = await world.call("POST", _path(ticket, "/help"), user=ALICE, json={"text": "n" * 1001})
    assert long.status_code == 422 and long.json()["detail"] == "Use up to 1000 characters."
    assert (await stored(world.db, ticket["id"]))["status"] == "pending_customer"
    assert (await world.call("POST", _path(ticket, "/help"), user=ALICE)).status_code == 200
    assert not [c for c in (await stored(world.db, ticket["id"]))["comments"] if c.get("kind") == "requester_reply"]


async def test_the_reporter_typing_on_the_portal_sends_it_to_a_person(world):
    """protects=D-31 through the real comment route: the same effect as the button, no second comment from the
    desk, no new job; fails_when=the ticket stays with the customer."""
    ticket = await _posted(world)
    typed = await world.call("POST", f"/api/tickets/{ticket['id']}/comments", user=ALICE, json={"text": "It did not work"})
    assert typed.status_code == 200
    after = await stored(world.db, ticket["id"])
    assert after["status"] == "open" and after["desk"]["phase"] == "helped"
    assert [c["text"] for c in after["comments"] if c.get("author") == "alice@x.co"] == ["It did not work"]
    assert await world.db.service_desk_jobs.count_documents({}) == 1
    handoffs = await world.db.autonomy_actions.count_documents({"command": "ticket_handoff", "tenantId": "t1"})
    assert handoffs == 1


async def test_a_staff_reply_to_the_requester_ends_undo_and_a_staff_note_does_not(world):
    """protects=UI-SPEC section 5 through the real comment route; fails_when=a note for staff ends Undo or a
    reply to the requester does not."""
    ticket = await _posted(world)
    note = await world.call("POST", f"/api/tickets/{ticket['id']}/comments", user=BOB, json={"text": SECRET})
    assert note.status_code == 200
    assert (await stored(world.db, ticket["id"]))["desk"]["undoable"] is True
    reply = await world.call("POST", f"/api/tickets/{ticket['id']}/comments", user=CAROL,
                             json={"text": "Restart and try again", "visibility": "requester"})
    assert reply.status_code == 200
    after = await stored(world.db, ticket["id"])
    assert after["desk"]["personReplied"] is True and after["desk"]["undoable"] is False
    assert after["status"] == "pending_customer"
    view = (await world.call("GET", _path(ticket), user=ALICE)).json()["requester"]
    assert view["canConfirm"] is True and SECRET not in str(view)


async def test_a_failing_hook_never_fails_the_comment(world, monkeypatch):
    """protects=the hook is advisory: the comment is stored and the route answers 200; fails_when=a hook error
    reaches the caller."""
    from service_desk import lifecycle

    async def boom(*args, **kwargs):
        raise RuntimeError("hook down")

    monkeypatch.setattr(lifecycle, "on_comment_added", boom)
    ticket = await _posted(world)
    response = await world.call("POST", f"/api/tickets/{ticket['id']}/comments", user=BOB, json={"text": "fine"})
    assert response.status_code == 200
    assert "fine" in str((await stored(world.db, ticket["id"]))["comments"])


# ---------------------------------------------------------------- Task 3: return date, names and cited articles

async def test_the_requester_view_gives_the_return_date_in_the_tenant_zone(world):
    """protects=D-08 / R3: returnAt is 3 working days after desk.postedAt in the tenant's zone, worked out on every
    read and never stored; it goes with the answer; fails_when=the zone is ignored, the date is stored or it
    stays after a confirmation."""
    ticket = await _posted(world)
    await world.db.maintenance_settings.insert_one({"tenantId": "t1", "timeZone": "America/New_York"})
    friday = datetime(2026, 10, 30, 20, 0, tzinfo=timezone.utc)                  # 16:00 in New York
    await world.db.tickets.update_one({"id": ticket["id"]}, {"$set": {"desk.postedAt": friday}})
    view = (await world.call("GET", _path(ticket), user=ALICE)).json()["requester"]
    assert view["returnAt"] == "2026-11-04T21:00:00+00:00"                       # Wednesday 16:00 after the clock change
    assert "returnAt" not in (await stored(world.db, ticket["id"]))["desk"]

    await world.db.maintenance_settings.delete_many({})
    assert (await world.call("GET", _path(ticket), user=ALICE)).json()["requester"]["returnAt"] == "2026-11-04T20:00:00+00:00"
    await world.db.tickets.update_one({"id": ticket["id"]}, {"$set": {"desk.postedAt": friday.isoformat()}})
    assert (await world.call("GET", _path(ticket), user=ALICE)).json()["requester"]["returnAt"] == "2026-11-04T20:00:00+00:00"

    await world.call("POST", _path(ticket, "/confirm"), user=ALICE)
    assert (await world.call("GET", _path(ticket), user=ALICE)).json()["requester"]["returnAt"] is None


@pytest.mark.parametrize("phase,notice", [("confirmed", "confirmed"), ("helped", "helped"), ("handed_off", "handed_off"),
                                          ("returned", "handed_off"), ("withdrawn", "withdrawn"), ("discarded", None),
                                          ("drafted", None), ("posted", None)])
async def test_the_notice_follows_the_desk_phase(world, phase, notice):
    """protects=UI-SPEC section 4 the panel states; fails_when=a phase shows the wrong notice (a discarded draft
    must show none)."""
    ticket = await _posted(world)
    await world.db.tickets.update_one({"id": ticket["id"]}, {"$set": {"desk.phase": phase}})
    assert (await world.call("GET", _path(ticket), user=ALICE)).json()["requester"]["notice"] == notice


async def test_a_reply_from_staff_shows_the_staff_name_or_none(world):
    """protects=R12: the profile name on the portal, no address when there is no profile; fails_when=an
    address is shown."""
    ticket = await _posted(world)
    nameless = portal_user("t1", "zed@x.co")
    await world.call("POST", f"/api/tickets/{ticket['id']}/comments", user=CAROL, json={"text": "One moment", "visibility": "requester"})
    await world.call("POST", f"/api/tickets/{ticket['id']}/comments", user=nameless, json={"text": "Me too", "visibility": "requester"})
    items = (await world.call("GET", _path(ticket), user=ALICE)).json()["requester"]["items"]
    by_text = {i["text"]: i for i in items}
    assert by_text["One moment"]["author"] == "Carol" and by_text["Me too"]["author"] is None
    assert by_text[ANSWER]["kind"] == "ai_answer"


async def test_a_withdrawn_answer_is_hidden_from_the_requester_and_kept_for_staff(world):
    """protects=D-25 the requester never reads a withdrawn answer; fails_when=it is listed."""
    ticket = await _posted(world)
    await world.db.tickets.update_one({"id": ticket["id"], "comments.kind": "ai_answer"},
                                      {"$set": {"comments.$.ai.state": "withdrawn"}})
    mine = await world.call("GET", _path(ticket), user=ALICE)
    assert mine.json()["requester"]["items"] == [] and ANSWER not in mine.text
    assert draft_of(await stored(world.db, ticket["id"]))["text"] == ANSWER


async def test_the_reporter_opens_only_the_articles_cited_on_their_answer(world):
    """protects=D-14 / T-85-51: the cited article opens read-only; an uncited article of the same tenant, a global
    one and an unknown id are 404; fails_when=a requester browses the knowledge base."""
    ticket = await _posted(world)
    opened = await world.call("GET", _path(ticket, "/articles/kb-pw"), user=ALICE)
    assert opened.status_code == 200
    body = opened.json()
    assert body["articleId"] == "kb-pw" and body["title"] == "Reset your own password" and body["available"] is True
    assert "Forgot password" in body["content"] and set(body) == {"articleId", "title", "content", "available"}
    for article in ("kb-vpn", "kb-global", "nope"):
        response = await world.call("GET", _path(ticket, f"/articles/{article}"), user=ALICE)
        assert response.status_code == 404 and response.json()["detail"] == messages.API_DETAIL["article_not_found"]
    assert (await world.call("GET", _path(ticket, "/articles/kb-pw"), user=STAFF2)).status_code == 404     # another tenant


async def test_a_deleted_or_unmarked_article_answers_unavailable_with_its_cited_title(world):
    """protects=D-14 the answer stays readable when its source goes; fails_when=a 404 or a 500 for a removed
    article, or the text is still served after the Help desk mark is removed."""
    ticket = await _posted(world)
    await world.db.knowledge_docs.update_one({"id": "kb-pw", "tenantId": "t1"}, {"$set": {"helpdesk": False}})
    first = (await world.call("GET", _path(ticket, "/articles/kb-pw"), user=ALICE)).json()
    assert first == {"articleId": "kb-pw", "title": "Reset your own password", "content": "", "available": False}
    await world.db.knowledge_docs.delete_one({"id": "kb-pw", "tenantId": "t1"})
    second = await world.call("GET", _path(ticket, "/articles/kb-pw"), user=ALICE)
    assert second.status_code == 200 and second.json() == first


async def test_a_citation_naming_a_global_article_never_serves_it(world):
    """protects=T-85-51 the read is scoped to the ticket's tenant: a forged citation of a global article gets
    unavailable and no text; fails_when=the global article's text is returned."""
    ticket = await _posted(world)
    await world.db.tickets.update_one({"id": ticket["id"], "comments.kind": "ai_answer"}, {"$push": {
        "comments.$.ai.citations": {"articleId": "kb-global", "title": "Forged"}}})
    body = (await world.call("GET", _path(ticket, "/articles/kb-global"), user=ALICE)).json()
    assert body == {"articleId": "kb-global", "title": "Forged", "content": "", "available": False}


async def test_staff_open_the_articles_of_the_waiting_draft_and_the_reporter_does_not(world):
    """protects=D-14 staff: the answer or the waiting draft; the reporter: only an answer they can see (a draft
    is not one); fails_when=either side differs, or a discarded draft's article stays open to staff."""
    ticket, comment = await _draft(world)
    assert (await world.call("GET", _path(ticket, "/articles/kb-pw"), user=STAFF2)).status_code == 200
    assert (await world.call("GET", _path(ticket, "/articles/kb-pw"), user=DRAFT_ALICE)).status_code == 404
    assert (await world.call("GET", _path(ticket, "/articles/kb-vpn"), user=STAFF2)).status_code == 404
    await world.call("POST", _path(ticket, f"/drafts/{comment['id']}/discard"), user=STAFF2)
    assert (await world.call("GET", _path(ticket, "/articles/kb-pw"), user=STAFF2)).status_code == 404
    sent, comment2 = await _draft(world)
    await world.call("POST", _path(sent, f"/drafts/{comment2['id']}/send"), user=STAFF2)
    assert (await world.call("GET", _path(sent, "/articles/kb-pw"), user=DRAFT_ALICE)).status_code == 200
