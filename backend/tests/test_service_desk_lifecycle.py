"""What people do with a desk answer (Phase 85, plan 85-14, DESK-01, decisions D-07 to D-10). Real MongoDB
(skips without one) through the throwaway database of tests/_mongo_test_db.py; the local model is a stand-in.

Value: protects=a waiting draft goes to the requester only when a person sends it, exactly once, under the
AI-assisted label with its citations; a discard sends nothing and starts no second attempt; a person's send is
never counted as an automatic answer; a requester's yes is the only way the desk resolves a ticket and a no or a
typed reply sends it to a person; fails_when=two sends both win, a closed ticket or a ticket a person already
answered still gets the draft, an edit is stored without the limits, a discard reaches the requester, a sent
row counts toward the desk's hourly pool, or any path of this module writes a closed status;
no_claim=the HTTP routes and their permission checks (test_service_desk_portal_routes.py) and the 3 working
day return (85-17).
"""
import asyncio
import os
import sys
from datetime import timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import ledger
from service_desk import lifecycle, messages
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.service_desk_portal_support import (ANSWER, DRAFT_ALICE, SHADOW_ALICE, at, build_world, desk_row, draft_of,
                                               notices, raise_and_run, stored)

NOW = at(2026, 11, 9, 14, 30)
BOB_ACTOR = {"id": "bob@x.co", "name": "Bob"}
CAROL_ACTOR = {"id": "carol@x.co", "name": "Carol"}


@pytest.fixture
async def world(mongo_db, monkeypatch):  # noqa: F811
    return await build_world(mongo_db, monkeypatch)


async def _draft(world, user=DRAFT_ALICE):
    """A ticket of the Drafts only tenant t2 with one waiting draft."""
    ticket = await raise_and_run(world, user)
    assert ticket["desk"]["draftWaiting"] is True
    return ticket, draft_of(ticket)


async def _send(world, ticket, comment, actor=BOB_ACTOR, tenant="t2", **kw):
    return await lifecycle.send_draft(world.db, tenant, ticket["id"], comment["id"], actor=actor, now=NOW, **kw)


# ---------------------------------------------------------------- send

async def test_sending_a_draft_as_it_is_answers_the_requester_once(world):
    """protects=D-09 a sent draft is a requester-visible AI answer with its citations, sentBy and the status
    pending_customer; fails_when=the comment stays staff-only, loses its mark or citations, or the ticket is not
    held for the customer."""
    ticket, comment = await _draft(world)
    assert comment["visibility"] == "staff" and comment["kind"] == "ai_draft"
    result = await _send(world, ticket, comment)
    assert result == {"status": "sent", "commentId": comment["id"], "edited": False}

    after = await stored(world.db, ticket["id"])
    sent = draft_of(after)
    assert (sent["kind"], sent["visibility"], sent["text"]) == ("ai_answer", "requester", ANSWER)
    assert sent["ai"]["state"] == "sent" and sent["ai"]["edited"] is False
    assert sent["ai"]["sentBy"] == BOB_ACTOR and sent["ai"]["sentAt"] == NOW.isoformat()
    assert [c["articleId"] for c in sent["ai"]["citations"]] == ["kb-pw"]
    assert after["status"] == "pending_customer"
    desk = after["desk"]
    assert desk["phase"] == "sent" and desk["draftWaiting"] is False and desk["undoable"] is True
    assert desk["sentBy"] == BOB_ACTOR and desk["edited"] is False and desk["postedAt"] is not None


async def test_the_sent_row_names_the_sender_and_is_never_counted_as_an_automatic_answer(world):
    """protects=D-09 / decision 8 / T-85-54: the suggestion becomes executed with the sender as approver and
    the Activity sentence; it is not autoDispatched, so the hourly pool and the breaker never count it;
    fails_when=the approver is empty, the sentence is the draft's, or the row counts as automatic."""
    ticket, comment = await _draft(world)
    before = await desk_row(world.db, ticket, "t2")
    assert before["state"] == "suggested" and before["approval"]["expiresAt"] is None
    await _send(world, ticket, comment)

    row = await desk_row(world.db, ticket, "t2")
    assert row["state"] == "executed" and row["approval"]["approver"]["display"] == "Bob"
    assert row["approval"]["approver"]["username"] == "bob@x.co"
    assert row["activityResult"] == "Sent by Bob at 14:30. Waiting for the requester."
    assert row["desk"]["phase"] == "sent" and row["desk"]["sentBy"] == BOB_ACTOR and row["desk"]["undoable"] is True
    assert row.get("autoDispatched") is not True
    since = NOW - timedelta(days=1)
    assert await ledger.count_auto_since(world.db, "t2", since, pool="servicedesk") == 0
    assert await ledger.recent_finished_auto(world.db, "t2") == []
    audit = await world.db.audit_logs.find({"tenantId": "t2", "action": "autonomous_ops.executed"}).to_list(5)
    assert len(audit) == 1 and audit[0]["actor"]["userId"] == "bob@x.co"


async def test_the_requester_gets_one_tagged_notice_when_the_answer_is_sent(world):
    """protects=D-33 one in-app notice for the reporter, carrying no text of the answer; fails_when=two notices,
    none, or one addressed to the tenant."""
    ticket, comment = await _draft(world)
    assert await notices(world.db, "alice@x.co") == []
    await _send(world, ticket, comment)
    [notice] = await notices(world.db, "alice@x.co", "answer_sent")
    assert notice["metadata"]["ticket_id"] == ticket["id"] and ANSWER not in str(notice)


async def test_an_edit_is_sent_under_the_same_mark_and_citations(world):
    """protects=D-09 / R8 the edited text replaces the draft's, the citations stay and cannot change;
    fails_when=the original text is sent, the citations change or ai.edited is False."""
    ticket, comment = await _draft(world)
    result = await _send(world, ticket, comment, text="  Choose Forgot password on the sign-in page.  ")
    assert result["status"] == "sent" and result["edited"] is True
    sent = draft_of(await stored(world.db, ticket["id"]))
    assert sent["text"] == "Choose Forgot password on the sign-in page." and sent["ai"]["edited"] is True
    assert sent["kind"] == "ai_answer" and [c["articleId"] for c in sent["ai"]["citations"]] == ["kb-pw"]
    assert (await desk_row(world.db, ticket, "t2"))["desk"]["edited"] is True


@pytest.mark.parametrize("text,reason", [("", "draft_empty"), ("   \n ", "draft_empty"), ("x" * 901, "draft_too_long"),
                                         (ANSWER, "edit_unchanged"), (f"  {ANSWER}\n", "edit_unchanged")])
async def test_an_edit_that_is_empty_too_long_or_unchanged_is_refused_and_the_draft_stays(world, text, reason):
    """protects=D-09 the 900 character limit and the unchanged rule; fails_when=the edit is accepted or the
    draft is touched by the refusal."""
    ticket, comment = await _draft(world)
    assert await _send(world, ticket, comment, text=text) == {"status": "refused", "reason": reason}
    after = await stored(world.db, ticket["id"])
    assert draft_of(after)["ai"]["state"] == "draft" and after["status"] == "open"
    assert (await desk_row(world.db, ticket, "t2"))["state"] == "suggested"


async def test_an_edit_of_exactly_900_characters_is_accepted(world):
    """protects=the limit is inclusive; fails_when=900 characters is refused."""
    ticket, comment = await _draft(world)
    assert (await _send(world, ticket, comment, text="y" * 900))["status"] == "sent"


# ---------------------------------------------------------------- the refusals

async def test_a_resolved_or_closed_ticket_cannot_be_sent_but_can_be_discarded(world):
    """protects=D-09 ticket_closed; fails_when=a resolved ticket gets the answer, the status moves, or the
    discard is refused."""
    for status in ("resolved", "closed"):
        ticket, comment = await _draft(world)
        await world.db.tickets.update_one({"id": ticket["id"]}, {"$set": {"status": status}})
        assert await _send(world, ticket, comment) == {"status": "refused", "reason": "ticket_closed", "state": status}
        assert draft_of(await stored(world.db, ticket["id"]))["ai"]["state"] == "draft"
        found = await lifecycle.discard_draft(world.db, "t2", ticket["id"], comment["id"], actor=BOB_ACTOR, now=NOW)
        assert found["status"] == "discarded"
        assert (await stored(world.db, ticket["id"]))["status"] == status


async def test_a_ticket_a_person_already_answered_cannot_get_the_draft(world):
    """protects=D-09 person_replied, both from the flag and from a plain requester-visible comment by someone
    else; fails_when=the draft goes out after a person replied, or the reporter's own comment blocks it."""
    ticket, comment = await _draft(world)
    reporters_own = {"id": "c1", "author": "alice@x.co", "text": "hello", "visibility": "requester",
                     "created_at": NOW.isoformat()}
    await world.db.tickets.update_one({"id": ticket["id"]}, {"$push": {"comments": reporters_own}})
    assert (await _send(world, ticket, comment, text="a new answer"))["status"] == "sent"      # not a person's reply

    other, comment2 = await _draft(world)
    staff_reply = {"id": "c2", "author": "carol@x.co", "text": "I'm on it", "visibility": "requester",
                   "created_at": NOW.isoformat()}
    await world.db.tickets.update_one({"id": other["id"]}, {"$push": {"comments": staff_reply}})
    assert await _send(world, other, comment2) == {"status": "refused", "reason": "person_replied", "state": "open"}

    third, comment3 = await _draft(world)
    await world.db.tickets.update_one({"id": third["id"]}, {"$set": {"desk.personReplied": True}})
    assert (await _send(world, third, comment3))["reason"] == "person_replied"


async def test_a_staff_only_comment_does_not_count_as_a_reply(world):
    """protects=D-11 a note for staff is not an answer to the requester; fails_when=it blocks the draft."""
    ticket, comment = await _draft(world)
    note = {"id": "n1", "author": "carol@x.co", "text": "checking", "visibility": "staff", "created_at": NOW.isoformat()}
    await world.db.tickets.update_one({"id": ticket["id"]}, {"$push": {"comments": note}})
    assert (await _send(world, ticket, comment))["status"] == "sent"


async def test_a_ticket_with_no_requester_who_can_read_it_cannot_be_sent(world):
    """protects=D-09 no_requester for a legacy tray ticket without My tickets; fails_when=it is sent."""
    ticket, comment = await _draft(world)
    await world.db.tickets.update_one({"id": ticket["id"]}, {"$set": {"requester_channel": {
        "portal": False, "tray": True, "myTickets": False}}})
    assert await _send(world, ticket, comment) == {"status": "refused", "reason": "no_requester", "state": "open"}


async def test_a_draft_already_sent_or_discarded_or_missing_is_already_handled(world):
    """protects=D-09 already_handled; fails_when=a second send or a send after a discard succeeds."""
    ticket, comment = await _draft(world)
    assert (await _send(world, ticket, comment))["status"] == "sent"
    assert await _send(world, ticket, comment, actor=CAROL_ACTOR) == {"status": "refused", "reason": "already_handled"}
    other, comment2 = await _draft(world)
    await lifecycle.discard_draft(world.db, "t2", other["id"], comment2["id"], actor=BOB_ACTOR, now=NOW)
    assert (await _send(world, other, comment2))["reason"] == "already_handled"
    assert (await _send(world, other, {"id": "nope"}))["reason"] == "already_handled"
    assert (await lifecycle.send_draft(world.db, "t2", "missing", "x", actor=BOB_ACTOR))["reason"] == "not_found"
    assert (await _send(world, ticket, comment, tenant="t1"))["reason"] == "not_found"          # another tenant


async def test_two_sends_at_once_give_one_winner_and_one_notice(world):
    """protects=T-85-53 compare-and-set on the comment state; fails_when=both sends win, or the requester is
    told twice."""
    ticket, comment = await _draft(world)
    results = await asyncio.gather(_send(world, ticket, comment, actor=BOB_ACTOR),
                                   _send(world, ticket, comment, actor=CAROL_ACTOR))
    assert sorted(r["status"] for r in results) == ["refused", "sent"]
    [loser] = [r for r in results if r["status"] == "refused"]
    assert loser["reason"] == "already_handled"
    assert len(await notices(world.db, "alice@x.co", "answer_sent")) == 1
    after = await stored(world.db, ticket["id"])
    assert len([h for h in after["history"] if h["action"] == "draft_sent"]) == 1


async def test_a_send_and_a_discard_at_once_give_one_winner(world):
    """protects=T-85-53 a discard and a send cannot both win; fails_when=the draft is sent and discarded."""
    ticket, comment = await _draft(world)
    sent, discarded = await asyncio.gather(
        _send(world, ticket, comment),
        lifecycle.discard_draft(world.db, "t2", ticket["id"], comment["id"], actor=CAROL_ACTOR, now=NOW))
    assert sorted([sent["status"], discarded["status"]]) in (["refused", "sent"], ["discarded", "refused"])
    assert draft_of(await stored(world.db, ticket["id"]))["ai"]["state"] in ("sent", "discarded")


async def test_the_compare_and_set_refuses_a_draft_that_was_discarded_or_sent_in_between(world):
    """protects=T-85-53 even when both callers read the draft before either wrote: the write itself checks the
    state; fails_when=a discarded or sent draft can be turned again."""
    ticket, comment = await _draft(world)
    await lifecycle.discard_draft(world.db, "t2", ticket["id"], comment["id"], actor=BOB_ACTOR, now=NOW)
    turn = lambda cid, key: lifecycle._turn_draft(  # noqa: E731
        world.db, "t2", ticket["id"], cid, {"ai.state": key}, actor=CAROL_ACTOR, action="x", now=NOW)
    assert await turn(comment["id"], "sent") is False
    other, comment2 = await _draft(world)
    await _send(world, other, comment2)
    assert await lifecycle._turn_draft(world.db, "t2", other["id"], comment2["id"], {"ai.state": "discarded"},
                                       actor=CAROL_ACTOR, action="x", now=NOW) is False
    assert draft_of(await stored(world.db, other["id"]))["ai"]["state"] == "sent"


# ---------------------------------------------------------------- discard

async def test_a_discard_keeps_the_draft_staff_only_and_starts_no_second_attempt(world):
    """protects=D-04 / D-10: the comment stays staff-only with state discarded, the row is denied, the ticket
    says discarded and nobody is told; fails_when=the requester is notified, a job is queued or the status
    moves."""
    ticket, comment = await _draft(world)
    jobs_before = await world.db.service_desk_jobs.count_documents({})
    result = await lifecycle.discard_draft(world.db, "t2", ticket["id"], comment["id"], actor=BOB_ACTOR, now=NOW)
    assert result == {"status": "discarded", "commentId": comment["id"]}

    after = await stored(world.db, ticket["id"])
    gone = draft_of(after)
    assert gone["visibility"] == "staff" and gone["kind"] == "ai_draft" and gone["ai"]["state"] == "discarded"
    assert gone["ai"]["discardedBy"] == BOB_ACTOR
    assert after["status"] == "open"
    assert after["desk"]["phase"] == "discarded" and after["desk"]["draftWaiting"] is False

    row = await desk_row(world.db, ticket, "t2")
    assert row["state"] == "denied" and row["desk"]["phase"] == "discarded" and row["desk"]["discardedBy"] == BOB_ACTOR
    assert row["activityResult"] == "Discarded by Bob."
    assert await notices(world.db, "alice@x.co") == []
    assert await world.db.service_desk_jobs.count_documents({}) == jobs_before
    assert (await lifecycle.discard_draft(world.db, "t2", ticket["id"], comment["id"], actor=BOB_ACTOR))["reason"] \
        == "already_handled"


# ---------------------------------------------------------------- shadow and refused rows

async def test_a_shadow_row_stays_shadow_with_desk_fields_and_one_audit_event(world):
    """protects=D-09 in shadow a send is a person's choice: the comment goes out, the row keeps its state and
    gets desk fields and a servicedesk.sent event; fails_when=the shadow row turns executed or no event is
    written."""
    ticket = await raise_and_run(world, SHADOW_ALICE)
    comment = draft_of(ticket)
    assert comment["kind"] == "ai_draft" and ticket["desk"]["draftReason"] == "shadow"
    row = await desk_row(world.db, ticket, "t3")
    assert row["state"] == "shadow"
    assert (await _send(world, ticket, comment, tenant="t3"))["status"] == "sent"

    after = await desk_row(world.db, ticket, "t3")
    assert after["state"] == "shadow" and after["desk"]["phase"] == "sent" and after["desk"]["sentBy"] == BOB_ACTOR
    assert after["activityResult"] == row["activityResult"]
    events = await world.db.audit_logs.find({"tenantId": "t3", "action": "autonomous_ops.servicedesk.sent"}).to_list(5)
    assert len(events) == 1 and events[0]["actor"]["userId"] == "bob@x.co"
    assert (await stored(world.db, ticket["id"]))["status"] == "pending_customer"


async def test_a_refused_row_gets_desk_fields_and_an_audit_event_on_discard(world):
    """protects=D-10 a row the gate refused is not moved by a person's discard; fails_when=its state changes."""
    ticket, comment = await _draft(world)
    row = await desk_row(world.db, ticket, "t2")
    await world.db.autonomy_actions.update_one({"id": row["id"]}, {"$set": {"state": "refused"}})
    assert (await lifecycle.discard_draft(world.db, "t2", ticket["id"], comment["id"], actor=BOB_ACTOR,
                                          now=NOW))["status"] == "discarded"
    after = await desk_row(world.db, ticket, "t2")
    assert after["state"] == "refused" and after["desk"]["phase"] == "discarded"
    events = await world.db.audit_logs.find({"tenantId": "t2", "action": "autonomous_ops.servicedesk.discarded"}).to_list(5)
    assert len(events) == 1


async def test_every_refusal_has_a_text_in_the_message_table():
    """protects=T-85-54 / the copy rule: each refusal code the lifecycle returns is a key of API_DETAIL;
    fails_when=a code has no text."""
    for code in ("not_found", "already_handled", "ticket_closed", "person_replied", "no_requester", "draft_empty",
                 "draft_too_long", "edit_unchanged"):
        assert messages.API_DETAIL[code]
    assert "{state}" in messages.API_DETAIL["ticket_closed"] and "{max}" in messages.API_DETAIL["draft_too_long"]
