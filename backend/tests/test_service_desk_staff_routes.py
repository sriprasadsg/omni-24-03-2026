"""The service desk routes under the ticket-staff rule (Phase 85 gap G-85-4, plan 85-35, WR-502, UD-2). Real MongoDB
(skips without one) through the throwaway database of tests/_mongo_test_db.py; the local model is a stand-in.

Value: protects=WR-502 / UD-2 / D-10 / D-14 / PROH-85-26 / T-85-121 / T-85-122 / T-85-123: only ticket staff who
did not raise a ticket see its waiting AI draft or send, edit and discard it, a colleague who is neither staff nor
the reporter gets the 404 of a ticket that does not exist, and the cited-article reader opens the staff list only
for staff who did not raise the ticket; fails_when=a colleague with view:dashboard reads or changes the draft or
the desk ledger row, the reporter (staff or not) is let through a draft route, or staff_view returns the panel
without the staff flag; no_claim=the lifecycle and the wording of the refusals (test_service_desk_portal_routes.py).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service_desk import messages, projection
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.service_desk_support import portal_user
from tests.service_desk_portal_support import (ALICE, ANSWER, BOB, DRAFT_ALICE, STAFF2, build_world, desk_row, draft_of,
                                               raise_and_run, stored)

ERIN = portal_user("t2", "erin@x.co")                    # a requester of the Drafts only tenant who did not raise it
ERIN_T1 = portal_user("t1", "erin@x.co")                 # the same on the Post answers tenant
ALICE_ADMIN = portal_user("t2", "alice@x.co", role="admin")        # the reporter, who is also staff (manage:tickets)


@pytest.fixture
async def world(mongo_db, monkeypatch):  # noqa: F811
    return await build_world(mongo_db, monkeypatch)


def _path(ticket, tail=""):
    return f"/api/tickets/{ticket['id']}/service-desk{tail}"


async def _draft(world):
    ticket = await raise_and_run(world, DRAFT_ALICE)
    return ticket, draft_of(ticket)


def _draft_calls(cid):
    return (("POST", f"/drafts/{cid}/send", None), ("POST", f"/drafts/{cid}/edit", {"text": "I decide"}),
            ("POST", f"/drafts/{cid}/discard", None))


async def test_a_colleague_who_is_not_staff_gets_404_everywhere_and_nothing_changes(world):
    """protects=T-85-121 / T-85-122: Erin gets the 404 sentence of a missing ticket on the view, the three draft
    routes, confirm, help and the cited-article reader; afterwards the draft is still waiting, the ticket is open
    and the desk row is as it was; fails_when=any call answers anything else or anything moves."""
    ticket, comment = await _draft(world)
    cid = comment["id"]
    row_before = await desk_row(world.db, ticket, "t2")
    calls = (("GET", "", None), ("POST", "/confirm", None), ("POST", "/help", {"text": "hi"}),
             ("GET", "/articles/kb-pw", None)) + _draft_calls(cid)
    for method, tail, body in calls:
        response = await world.call(method, _path(ticket, tail), user=ERIN, json=body)
        assert response.status_code == 404, (method, tail, response.text)
        assert response.json()["detail"] == messages.API_DETAIL["not_found"], (method, tail)
    after = await stored(world.db, ticket["id"])
    assert draft_of(after)["ai"]["state"] == "draft" and after["status"] == "open" and draft_of(after)["text"] == ANSWER
    assert await desk_row(world.db, ticket, "t2") == row_before


async def test_staff_who_did_not_raise_the_ticket_get_the_draft_and_can_discard_it(world):
    """protects=D-09 / D-10: STAFF2 reads the waiting draft, draftWaiting and canReplyToRequester and discards it;
    fails_when=the staff panel is gone or the discard is refused."""
    ticket, comment = await _draft(world)
    body = (await world.call("GET", _path(ticket), user=STAFF2)).json()
    assert body["isRequester"] is False and body["draftWaiting"] is True and body["canReplyToRequester"] is True
    assert body["draft"]["commentId"] == comment["id"] and body["draft"]["answer"] == ANSWER
    response = await world.call("POST", _path(ticket, f"/drafts/{comment['id']}/discard"), user=STAFF2)
    assert response.status_code == 200 and response.json()["status"] == "discarded"


async def test_the_reporter_gets_the_requester_view_and_the_staff_only_refusal_on_the_draft_routes(world):
    """protects=PROH-85-26 / D-10: the reporter sees no draft and is refused 403 staff_only on the three draft
    routes, the ticket untouched; fails_when=the reporter's response carries the draft or a route lets them in."""
    ticket, comment = await _draft(world)
    mine = (await world.call("GET", _path(ticket), user=DRAFT_ALICE)).json()
    assert mine["isRequester"] is True and mine["draft"] is None and mine["draftWaiting"] is False
    assert mine["canReplyToRequester"] is False
    for method, tail, body in _draft_calls(comment["id"]):
        response = await world.call(method, _path(ticket, tail), user=DRAFT_ALICE, json=body)
        assert response.status_code == 403 and response.json()["detail"] == messages.API_DETAIL["staff_only"], tail
    assert draft_of(await stored(world.db, ticket["id"]))["ai"]["state"] == "draft"


async def test_a_reporter_who_is_staff_still_gets_the_requester_view_and_no_draft_rights(world):
    """protects=UD-2 / PROH-85-26: a reporter holding manage:tickets is the requester on their own ticket: no
    draft, canReplyToRequester false, 403 staff_only on the three draft routes; fails_when=staff status lets the
    reporter read or act on their own draft."""
    ticket, comment = await _draft(world)
    mine = (await world.call("GET", _path(ticket), user=ALICE_ADMIN)).json()
    assert mine["isRequester"] is True and mine["draft"] is None and mine["draftWaiting"] is False
    assert mine["canReplyToRequester"] is False and mine["requester"] is not None
    for method, tail, body in _draft_calls(comment["id"]):
        response = await world.call(method, _path(ticket, tail), user=ALICE_ADMIN, json=body)
        assert response.status_code == 403 and response.json()["detail"] == messages.API_DETAIL["staff_only"], tail
    assert draft_of(await stored(world.db, ticket["id"]))["ai"]["state"] == "draft"


async def test_the_cited_article_reader_opens_the_staff_list_only_for_staff_who_did_not_raise_the_ticket(world):
    """protects=D-14 / T-85-123: on the posted answer the reporter and staff open kb-pw and a colleague gets 404;
    on the waiting draft staff open the draft's citation and the reporter (staff or not) does not (404
    article_not_found); fails_when=a non-staff colleague, or the reporter on a draft citation, gets the article."""
    posted = await raise_and_run(world, ALICE)
    assert (await world.call("GET", _path(posted, "/articles/kb-pw"), user=ALICE)).status_code == 200
    assert (await world.call("GET", _path(posted, "/articles/kb-pw"), user=BOB)).status_code == 200
    colleague = await world.call("GET", _path(posted, "/articles/kb-pw"), user=ERIN_T1)
    assert colleague.status_code == 404 and colleague.json()["detail"] == messages.API_DETAIL["not_found"]

    ticket, _ = await _draft(world)
    assert (await world.call("GET", _path(ticket, "/articles/kb-pw"), user=STAFF2)).status_code == 200
    for reporter in (DRAFT_ALICE, ALICE_ADMIN):
        refused = await world.call("GET", _path(ticket, "/articles/kb-pw"), user=reporter)
        assert refused.status_code == 404 and refused.json()["detail"] == messages.API_DETAIL["article_not_found"]


async def test_staff_view_needs_the_staff_flag(world):
    """protects=T-85-122: staff_view without the flag returns None for a non-reporter, with it returns the panel,
    and the reporter never gets one; fails_when=the default is not False."""
    ticket, _ = await _draft(world)
    assert projection.staff_view(ticket, None, STAFF2) is None
    panel = projection.staff_view(ticket, None, STAFF2, staff=True)
    assert panel is not None and panel["answer"] == ANSWER
    assert projection.staff_view(ticket, None, DRAFT_ALICE, staff=True) is None
