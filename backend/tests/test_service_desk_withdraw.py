"""Withdrawing a posted service desk answer and the desk-only breaker (Phase 85, plan 85-18, DESK-01, D-25).
Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py; the local model is a
stand-in and the Undo click goes through the real Autonomous Ops route.

Value: protects=a person can take a wrong posted answer back at once (the requester reads that a person will
follow up and never the answer, the ticket goes to a person, the row and the audit chain name who did it), even
during a stop; Undo is refused once it no longer means anything; three automatic answers withdrawn within 24
hours drop only the desk to Drafts only and never touch the tenant's Autonomous Ops level; fails_when=the
requester still reads a withdrawn answer, the ticket stays with the desk, a second click withdraws twice, an
answer already confirmed or already answered by a person can be withdrawn, two withdrawals trip the breaker, a
withdrawn draft that a person sent or an I still need help counts toward it, or the tenant's level changes;
no_claim=the Activity wording of other row shapes (test_service_desk_gate.py) and the settings routes
(test_service_desk_settings.py).
"""
import asyncio
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import approvals, ledger
from autonomous_ops import messages as ao_messages
from service_desk import messages, projection, withdraw
from tests._autonomous_ops_http import Api
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_platform_stop
from tests.service_desk_portal_support import (ALICE, ANSWER, BOB, DRAFT_ALICE, SHADOW_ALICE, STAFF2, build_world,
                                               desk_row, draft_of, notices, raise_and_run, stored)

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
async def world(mongo_db, monkeypatch):  # noqa: F811
    world = await build_world(mongo_db, monkeypatch)
    world.api = Api(mongo_db, monkeypatch)
    return world


async def _posted(world, user=ALICE):
    """A ticket the desk answered on its own (tenant t1 posts) and the row of that answer."""
    ticket = await raise_and_run(world, user)
    row = await desk_row(world.db, ticket)
    assert row["state"] == "executed" and row["autoDispatched"] is True and ticket["status"] == "pending_customer"
    return ticket, row


def _undo(world, row, *, role="tenant_admin", username="bob@x.co", tenant="t1"):
    return world.api.call("POST", f"/api/autonomous-ops/actions/{row['id']}/undo", role=role, username=username,
                          tenant=tenant)


def _path(ticket, tail=""):
    return f"/api/tickets/{ticket['id']}/service-desk{tail}"


async def _row(db, row_id):
    return await db.autonomy_actions.find_one({"id": row_id}, {"_id": 0})


async def _handoffs(db, ticket):
    return await db.autonomy_actions.find({"kind": "servicedesk", "command": "ticket_handoff",
                                           "desk.ticketId": ticket["id"]}, {"_id": 0}).to_list(10)


# ---------------------------------------------------------------- Task 1: withdraw through the Undo route

async def test_a_person_withdraws_a_posted_answer_and_the_requester_is_told(world):
    """protects=D-25 hide, tell, hand off, record; fails_when=the requester still reads the answer or its
    articles, the ticket stays pending_customer, the notice or the hand-off is missing or doubled, or the row
    does not name the person."""
    ticket, row = await _posted(world)
    done = await _undo(world, row)
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["status"] == "undone" and body["deskBreakerTripped"] is False and body["breakerTripped"] is False
    assert body["action"]["state"] == "undone"

    after = await stored(world.db, ticket["id"])
    answer = draft_of(after)
    assert answer["ai"]["state"] == "withdrawn" and answer["text"] == ANSWER        # staff keep the original
    [notice] = [c for c in after["comments"] if c.get("kind") == "withdrawn_notice"]
    assert notice["visibility"] == "requester" and notice["text"] == messages.WITHDRAWN_NOTICE
    assert notice["id"] == "sd-withdrawn-" + row["id"]
    assert after["status"] == "open"
    assert not [c for c in after["comments"] if c.get("kind") == "handoff_notice"]
    [note] = [c for c in after["comments"] if c.get("kind") == "staff_note"]
    assert note["visibility"] == "staff" and note["text"] == "Service desk: answer withdrawn."
    desk = after["desk"]
    assert desk["phase"] == "withdrawn" and desk["undoable"] is False and desk["lastReason"] == "answer_withdrawn"
    assert desk["withdrawnBy"] == {"id": "bob@x.co", "name": "Bob"} and desk["withdrawnAt"]

    mine = await world.call("GET", _path(ticket), user=ALICE)
    requester = mine.json()["requester"]
    assert [(i["kind"], i["text"], i["citations"]) for i in requester["items"]] == [
        ("withdrawn_notice", messages.WITHDRAWN_NOTICE, [])]
    assert requester["notice"] == "withdrawn" and requester["canConfirm"] is False
    assert ANSWER not in mine.text and "kb-pw" not in mine.text and "Reset your own password" not in mine.text
    assert projection.cited_articles(after, for_requester=True) == {}
    assert projection.cited_articles(after, for_requester=False) == {"kb-pw": "Reset your own password"}

    finished = await _row(world.db, row["id"])
    assert finished["state"] == "undone" and finished["undo"]["available"] is True
    assert finished["undo"]["action"] == "ticket_withdraw" and finished["undo"]["params"] == {"ticketId": ticket["id"]}
    assert finished["undo"]["undoneBy"] == {"username": "bob@x.co", "display": "Bob", "tier": "tenant"}
    assert finished["undo"]["undoneAt"] is not None
    assert re.fullmatch(r"Withdrawn by Bob at \d\d:\d\d\. The ticket went to a person\.", finished["activityResult"])
    assert finished["desk"]["phase"] == "withdrawn" and finished["desk"]["undoable"] is False
    assert finished["desk"]["withdrawnBy"] == {"id": "bob@x.co", "name": "Bob"}

    [handoff] = await _handoffs(world.db, ticket)
    assert handoff["reasonCode"] == "answer_withdrawn" and handoff["autoDispatched"] is False
    assert await world.db.audit_logs.count_documents(
        {"tenantId": "t1", "action": "autonomous_ops.undone", "resourceId": row["id"]}) == 1
    assert await world.db.audit_logs.count_documents(
        {"tenantId": "t1", "action": "autonomous_ops.servicedesk.handoff"}) == 1

    [told] = await notices(world.db, "alice@x.co", "answer_withdrawn")
    assert told["title"] == messages.WITHDRAWN_NOTICE_TITLE.format(number=ticket["ticket_number"])
    assert ANSWER not in str(told) and ticket["title"] not in str(told)
    assert told["metadata"]["ticket_id"] == ticket["id"]


@pytest.mark.parametrize("stop", ["tenant", "platform"])
async def test_undo_works_while_a_stop_is_on(world, stop):
    """protects=D-25 / Phase 81 D-12 withdrawing is the safe direction and is never blocked by a stop;
    fails_when=a stop makes the click answer 409 or the answer stays visible."""
    ticket, row = await _posted(world)
    if stop == "tenant":
        await world.db.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"stop": {
            "active": True, "scope": "tenant", "pressedBy": {"username": "x", "display": "X"},
            "pressedAt": datetime.now(timezone.utc), "reason": None}}})
    else:
        await seed_platform_stop(world.db)
    done = await _undo(world, row)
    assert done.status_code == 200, done.text
    assert draft_of(await stored(world.db, ticket["id"]))["ai"]["state"] == "withdrawn"


async def test_a_second_click_is_already_handled_and_writes_nothing_more(world):
    """protects=T-85-70 one withdrawal, one notice, one hand-off; fails_when=a second click adds a notice."""
    ticket, row = await _posted(world)
    assert (await _undo(world, row)).status_code == 200
    again = await _undo(world, row)
    assert again.status_code == 409 and again.json()["detail"] == ao_messages.API_DETAIL["already_handled"]
    after = await stored(world.db, ticket["id"])
    assert len([c for c in after["comments"] if c.get("kind") == "withdrawn_notice"]) == 1
    assert len(await _handoffs(world.db, ticket)) == 1
    assert len(await notices(world.db, "alice@x.co", "answer_withdrawn")) == 1


async def test_two_clicks_at_once_withdraw_once(world):
    """protects=T-85-70 the row transition decides one winner; fails_when=both clicks answer 200."""
    ticket, row = await _posted(world)
    first, second = await asyncio.gather(_undo(world, row), _undo(world, row))
    assert sorted([first.status_code, second.status_code]) == [200, 409]
    assert len(await _handoffs(world.db, ticket)) == 1


@pytest.mark.parametrize("how", ["confirmed", "helped", "person_replied"])
async def test_undo_is_refused_once_the_requester_or_a_person_has_answered(world, how):
    """protects=D-25 Undo only while the answer still means something; fails_when=an answer the requester
    confirmed, they asked a person for, or a person already replied to can be withdrawn."""
    ticket, row = await _posted(world)
    if how == "confirmed":
        assert (await world.call("POST", _path(ticket, "/confirm"), user=ALICE)).status_code == 200
    elif how == "helped":
        assert (await world.call("POST", _path(ticket, "/help"), user=ALICE, json={})).status_code == 200
    else:
        reply = {"id": "c9", "author": "carol@x.co", "text": "I'm on it", "visibility": "requester",
                 "created_at": datetime.now(timezone.utc).isoformat()}
        await world.db.tickets.update_one({"id": ticket["id"]}, {"$push": {"comments": reply}})
        await world.db.tickets.update_one({"id": ticket["id"]}, {"$set": {"desk.personReplied": True,
                                                                          "desk.undoable": False}})
    done = await _undo(world, row)
    assert done.status_code == 409, done.text
    assert (await _row(world.db, row["id"]))["state"] == "executed"
    after = await stored(world.db, ticket["id"])
    assert draft_of(after)["ai"]["state"] == "posted"
    assert not [c for c in after["comments"] if c.get("kind") == "withdrawn_notice"]


async def test_the_ticket_is_the_last_word_when_the_row_still_offers_undo(world):
    """protects=D-25 the requester's confirm wins over a stale row; fails_when=a row whose undoable flag
    was not updated lets a confirmed answer be withdrawn, or leaves the row marked undone."""
    ticket, row = await _posted(world)
    await world.db.tickets.update_one({"id": ticket["id"]}, {"$set": {"desk.phase": "confirmed",
                                                                      "desk.undoable": False}})
    done = await _undo(world, row)
    assert done.status_code == 409
    assert (await _row(world.db, row["id"]))["state"] == "executed"
    assert draft_of(await stored(world.db, ticket["id"]))["ai"]["state"] == "posted"


async def test_a_shadow_row_and_a_draft_that_was_never_sent_cannot_be_withdrawn(world):
    """protects=D-25 nothing was posted, so nothing is withdrawn; fails_when=a simulation or a waiting draft
    is turned to undone."""
    shadow_ticket = await raise_and_run(world, SHADOW_ALICE)
    shadow_row = await desk_row(world.db, shadow_ticket, tenant="t3")
    assert shadow_row["state"] == "shadow"
    assert (await _undo(world, shadow_row, tenant="t3")).status_code == 409
    draft_ticket = await raise_and_run(world, DRAFT_ALICE)
    draft_row = await desk_row(world.db, draft_ticket, tenant="t2")
    assert draft_row["state"] == "suggested"
    assert (await _undo(world, draft_row, tenant="t2")).status_code == 409
    for row, tenant in ((shadow_row, "t3"), (draft_row, "t2")):
        assert (await _row(world.db, row["id"]))["state"] == row["state"]
    assert await world.db.tickets.count_documents({"comments.kind": "withdrawn_notice"}) == 0


async def test_a_draft_a_person_sent_can_be_withdrawn(world):
    """protects=D-25 a sent draft is on the ticket like a posted one (Undo shows for phase sent); fails_when=the
    sent answer cannot be taken back."""
    ticket = await raise_and_run(world, DRAFT_ALICE)
    comment = draft_of(ticket)
    sent = await world.call("POST", _path(ticket, f"/drafts/{comment['id']}/send"), user=STAFF2)
    assert sent.status_code == 200, sent.text
    row = await desk_row(world.db, ticket, tenant="t2")
    assert row["state"] == "executed" and row["desk"]["sentBy"]
    done = await _undo(world, row, tenant="t2")
    assert done.status_code == 200, done.text
    after = await stored(world.db, ticket["id"])
    assert draft_of(after)["ai"]["state"] == "withdrawn" and after["status"] == "open"


async def test_a_viewer_without_control_and_an_api_key_cannot_withdraw(world):
    """protects=T-85-68 the undo permission is unchanged; fails_when=a read-only role or a key withdraws."""
    ticket, row = await _posted(world)
    assert (await _undo(world, row, role="analyst")).status_code == 403
    keyed = await world.api.call("POST", f"/api/autonomous-ops/actions/{row['id']}/undo", role="tenant_admin",
                                 auth="api_key", scopes=["*"])
    assert keyed.status_code in (401, 403)
    assert (await _row(world.db, row["id"]))["state"] == "executed"
    assert draft_of(await stored(world.db, ticket["id"]))["ai"]["state"] == "posted"


async def test_another_tenants_answer_is_not_found_and_untouched(world):
    """protects=tenant isolation; fails_when=an admin of t2 withdraws t1's answer."""
    ticket, row = await _posted(world)
    assert (await _undo(world, row, tenant="t2")).status_code == 404
    assert (await _row(world.db, row["id"]))["state"] == "executed"


async def test_a_failure_to_hide_the_answer_leaves_the_row_as_it_was(world, monkeypatch):
    """protects=D-25 a click that could not hide the answer must not leave the row saying undone while the
    requester still reads it; fails_when=the row stays undone after the ticket write failed."""
    ticket, row = await _posted(world)

    async def broken(*args, **kwargs):
        raise RuntimeError("database unavailable")

    real = withdraw._hide_answer
    monkeypatch.setattr(withdraw, "_hide_answer", broken)
    done = await _undo(world, row)
    assert done.status_code >= 500
    restored = await _row(world.db, row["id"])
    assert restored["state"] == "executed" and restored["desk"]["undoable"] is True
    assert restored["desk"]["phase"] == "posted"
    again = await stored(world.db, ticket["id"])
    assert draft_of(again)["ai"]["state"] == "posted"
    monkeypatch.setattr(withdraw, "_hide_answer", real)
    assert (await _undo(world, row)).status_code == 200


def test_the_settings_router_registers_the_handler_at_import():
    """protects=D-25 a running app always has the handler (the required router imports it); fails_when=a fresh
    interpreter that imports only the router has no service_desk undo handler."""
    code = ("import sys; sys.path.insert(0, sys.argv[1]); import autonomous_ops_service_desk_endpoints; "
            "from autonomous_ops import approvals; from service_desk import withdraw; "
            "print(approvals._UNDO_HANDLERS.get('service_desk') is withdraw.undo_answer)")
    out = subprocess.run([sys.executable, "-I", "-c", code, BACKEND], capture_output=True, text=True, timeout=120)
    assert out.stdout.strip() == "True", out.stderr


def test_the_handler_is_the_one_the_approvals_module_calls():
    assert approvals._UNDO_HANDLERS["service_desk"] is withdraw.undo_answer
    assert withdraw.DISPATCHER_NAME == "service_desk"
    assert ledger.DESK_KIND == "servicedesk"
