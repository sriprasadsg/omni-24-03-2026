"""What the tray user does with an answer (Phase 85, plan 85-19, DESK-01, decisions D-07, D-14, D-34): This fixed
it, I still need help and reading a cited article. Real MongoDB (skips without one) through the throwaway
database of tests/_mongo_test_db.py; the agent-key check is the production code with a signed agent token.

Value: protects=the same lifecycle as the portal runs for a tray user's own ticket and for nobody else's, and a
cited article is read only from the caller's own answer and only from the caller's own Help desk set;
fails_when=another Windows user, another computer, another tenant or a token for another agent can confirm, ask
for a person or read an article of a ticket it does not own, an uncited, global, other-tenant or unmarked
article is served, or a withdrawn answer's or a draft's citation opens an article; no_claim=the lifecycle edge
cases (test_service_desk_lifecycle.py) and how the buttons look.
"""
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service_desk import messages, tray_contract
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.service_desk_portal_support import PW_CONTENT, PW_TITLE, VPN_CONTENT
from tests.service_desk_support import seed_article
from tests.service_desk_tray_support import JDOE, build_tray_world, raised_and_answered, say, seed_ticket


@pytest.fixture
async def world(mongo_db, monkeypatch):  # noqa: F811
    return await build_tray_world(mongo_db, monkeypatch)


async def _unchanged(world, ticket):
    stored = await world.stored(ticket["id"])
    assert stored["status"] == "pending_customer" and stored["desk"]["phase"] == "posted"
    assert not [c for c in stored["comments"] if c.get("kind") == "requester_reply"]


async def _cites(world, ticket, comment_id, *article_ids, kind="ai_answer", visibility="requester", state="posted"):
    ai = {"actionId": comment_id, "state": state, "citations": [{"articleId": a, "title": "cited " + a} for a in article_ids]}
    await say(world, ticket, comment_id, kind, "some answer", visibility=visibility, ai=ai, at=datetime.now(timezone.utc))


# ---------------------------------------------------------------- This fixed it

async def test_this_fixed_it_resolves_the_ticket_like_the_portal_button(world):
    """protects=D-07 the same lifecycle as the portal; fails_when=the ticket is not resolved by the requester's
    confirmation, the desk fields do not say confirmed, or the list still offers the buttons."""
    ticket = await raised_and_answered(world)
    response = await world.post("a1", ticket, "confirm", {"user": " JDOE "})          # the match ignores case and spaces
    assert response.status_code == 200 and response.json() == {"status": "confirmed"}
    stored = await world.stored(ticket["id"])
    assert stored["status"] == "resolved" and stored["resolved_at"] and stored["desk"]["phase"] == "confirmed"
    assert stored["desk"]["undoable"] is False
    [shown] = (await world.list()).json()["tickets"]
    assert shown["statusText"] == messages.TRAY_STATUS_TEXT["resolved"] and shown["canConfirm"] is False
    assert (await world.post("a1", ticket, "confirm", {"user": JDOE})).status_code == 409      # nothing waits any more


async def test_a_ticket_with_no_answer_waiting_cannot_be_confirmed_or_helped(world):
    """protects=D-07 the buttons act only on an answer that waits; fails_when=a confirm or a help on a fresh
    ticket is accepted, or the refusal has other words than the table."""
    ticket = await seed_ticket(world)
    for action, body in (("confirm", {"user": JDOE}), ("help", {"user": JDOE, "text": "hello"})):
        response = await world.post("a1", ticket, action, body)
        assert response.status_code == 409 and response.json()["detail"] == messages.API_DETAIL["not_confirmable"]
    assert (await world.stored(ticket["id"]))["status"] == "open"


@pytest.mark.parametrize("action,body", [("confirm", {"user": JDOE}), ("help", {"user": JDOE, "text": "no"})])
async def test_only_the_owner_acts_on_a_ticket(world, action, body):
    """protects=T-85-72 / D-34 ownership is tenant, computer and Windows user, and a refusal says only 404;
    fails_when=another user, another computer, another tenant, a token for another agent or an unknown id acts."""
    ticket = await raised_and_answered(world)
    other_user = await world.post("a1", ticket, action, {**body, "user": "other"})
    other_computer = await world.post("a2", ticket, action, body)                    # a2, its own token and path
    other_tenant = await world.post("b1", ticket, action, body)                      # an agent of another tenant
    stranger = await world.post("a1", {"id": "no-such-ticket"}, action, body)
    for response in (other_user, other_computer, other_tenant, stranger):
        assert response.status_code == 404, response.text
        assert response.json()["detail"] == messages.API_DETAIL["not_found"]
    wrong_token = await world.call("POST", f"/api/agents/a1/tray/tickets/{ticket['id']}/{action}", agent="a2", json=body)
    assert wrong_token.status_code == 403
    no_token = await world.call("POST", f"/api/agents/a1/tray/tickets/{ticket['id']}/{action}", headers={}, json=body)
    assert no_token.status_code == 401
    await _unchanged(world, ticket)


async def test_an_old_trays_ticket_cannot_be_acted_on_through_the_tray_routes(world):
    """protects=D-05 the tray routes act on a ticket of a tray that can read the answer; fails_when=a ticket whose
    channel says myTickets False is confirmed."""
    ticket = await seed_ticket(world, my_tickets=False)
    await world.db.tickets.update_one({"id": ticket["id"]}, {"$set": {"status": "pending_customer",
                                                                      "desk": {"phase": "posted"}}})
    assert (await world.post("a1", ticket, "confirm", {"user": JDOE})).status_code == 404
    assert (await world.stored(ticket["id"]))["status"] == "pending_customer"


# ---------------------------------------------------------------- I still need help

async def test_i_still_need_help_sends_the_ticket_to_a_person(world):
    """protects=D-07 / D-31 the same lifecycle as the portal; fails_when=the ticket stays with the customer, the
    note is lost or shown as someone else's, no hand-off is recorded, or the requester is sent a second notice."""
    ticket = await raised_and_answered(world)
    response = await world.post("a1", ticket, "help", {"user": JDOE, "text": "  still broken  "})
    assert response.status_code == 200 and response.json() == {"status": "helped"}
    stored = await world.stored(ticket["id"])
    assert stored["status"] == "open" and stored["desk"]["phase"] == "helped" and stored["desk"]["lastReason"] == "did_not_help"
    [note] = [c for c in stored["comments"] if c.get("kind") == "requester_reply"]
    assert note["text"] == "still broken" and note["author"] == "tray:a1" and note["visibility"] == "requester"
    assert [c["text"] for c in stored["comments"] if c.get("kind") == "staff_note"] == [
        messages.STAFF_NOTE.format(label=messages.STAFF_REASON_LABELS["did_not_help"])]
    assert not [c for c in stored["comments"] if c.get("kind") == "handoff_notice"]
    [shown] = (await world.list()).json()["tickets"]
    assert [e["kind"] for e in shown["entries"]] == ["answer", "you"] and shown["entries"][1]["text"] == "still broken"
    assert shown["canConfirm"] is False and shown["statusText"] == messages.TRAY_STATUS_TEXT["with_it"]
    assert "did_not_help" not in (await world.list()).text and "did not help" not in (await world.list()).text


async def test_the_note_is_optional_and_stops_at_500_characters(world):
    """protects=T-85-75 the note is bounded where it comes in; fails_when=501 characters are accepted, or
    exactly 500 or no note at all is refused."""
    ticket = await raised_and_answered(world)
    too_long = await world.post("a1", ticket, "help", {"user": JDOE, "text": "n" * (tray_contract.NOTE_MAX + 1)})
    assert too_long.status_code == 422
    await _unchanged(world, ticket)
    exact = await raised_and_answered(world)
    assert (await world.post("a1", exact, "help", {"user": JDOE, "text": "n" * tray_contract.NOTE_MAX})).status_code == 200
    bare = await raised_and_answered(world)
    assert (await world.post("a1", bare, "help", {"user": JDOE})).status_code == 200
    assert not [c for c in (await world.stored(bare["id"]))["comments"] if c.get("kind") == "requester_reply"]


async def test_the_user_name_is_required_on_every_post(world):
    ticket = await raised_and_answered(world)
    for action in ("confirm", "help"):
        for body in ({}, {"user": ""}, {"user": "   "}, {"text": "x"}):
            assert (await world.post("a1", ticket, action, body)).status_code == 422, (action, body)
    await _unchanged(world, ticket)


# ---------------------------------------------------------------- cited articles

async def test_a_cited_article_is_read_from_the_callers_own_answer(world):
    """protects=D-14 the article of the answer the requester reads; fails_when=the title, text or flag differ, or
    the response carries more than the contract's fields."""
    ticket = await raised_and_answered(world)
    response = await world.article("a1", ticket, "kb-pw", user="JDoe")
    assert response.status_code == 200
    assert response.json() == {"title": PW_TITLE, "content": PW_CONTENT, "available": True}
    assert set(response.json()) == set(tray_contract.ARTICLE_FIELDS)


async def test_only_an_article_cited_on_this_ticket_opens(world):
    """protects=T-85-74 the allow-list is the callers visible, not withdrawn answer; fails_when=an uncited, a
    drafted, a withdrawn or an unknown article opens, or the refusal gives another status."""
    ticket = await raised_and_answered(world)
    await _cites(world, ticket, "sd-draft", "kb-vpn", kind="ai_draft", visibility="staff", state="draft")
    await _cites(world, ticket, "sd-gone", "kb-gone", state="withdrawn")
    await seed_article(world.db, "t1", "kb-gone", title="Withdrawn article", content="only the withdrawn answer cited it")
    for article_id in ("kb-vpn", "kb-gone", "kb-global", "no-such-article"):
        response = await world.article("a1", ticket, article_id)
        assert response.status_code == 404, article_id
        assert response.json()["detail"] == messages.API_DETAIL["article_not_found"]
    assert VPN_CONTENT not in (await world.article("a1", ticket, "kb-vpn")).text


async def test_a_citation_never_opens_a_global_foreign_or_unmarked_article(world):
    """protects=T-85-74 the article is read from this tenant's own Help desk set; fails_when=a cited id that is
    global, of another tenant, removed from the Help desk set or deleted returns its text."""
    ticket = await seed_ticket(world)
    await seed_article(world.db, "t2", "kb-t2-only", title="Another tenant", content="another tenant's secret")
    await seed_article(world.db, "t1", "kb-unmarked", title="Not in Help desk", content="not for the desk", helpdesk=False)
    await _cites(world, ticket, "sd-1", "kb-global", "kb-t2-only", "kb-unmarked", "kb-deleted", "kb-pw")
    await world.db.tickets.update_one({"id": ticket["id"]}, {"$set": {"status": "pending_customer",
                                                                      "desk": {"phase": "posted"}}})
    for article_id in ("kb-global", "kb-t2-only", "kb-unmarked", "kb-deleted"):
        response = await world.article("a1", ticket, article_id)
        assert response.status_code == 200, article_id
        assert response.json() == {"title": "cited " + article_id, "content": "", "available": False}
    await world.db.knowledge_docs.delete_one({"id": "kb-pw", "tenantId": "t1"})
    assert (await world.article("a1", ticket, "kb-pw")).json() == {"title": "cited kb-pw", "content": "", "available": False}


async def test_only_the_owner_reads_an_article(world):
    """protects=T-85-72 / D-34 an article opens for the owner of the ticket only; fails_when=another user, another
    computer, another tenant or another agent's token reads it."""
    ticket = await raised_and_answered(world)
    for agent, user in (("a1", "other"), ("a2", JDOE), ("b1", JDOE)):
        assert (await world.article(agent, ticket, "kb-pw", user=user)).status_code == 404, (agent, user)
    path = f"/api/agents/a1/tray/tickets/{ticket['id']}/articles/kb-pw"
    assert (await world.call("GET", path, agent="a2", params={"user": JDOE})).status_code == 403
    assert (await world.call("GET", path, headers={}, params={"user": JDOE})).status_code == 401
    assert (await world.call("GET", path)).status_code == 422                          # the user is required


# ---------------------------------------------------------------- the legacy route stays a draft

async def test_the_same_ticket_through_the_legacy_route_stays_a_draft(world):
    """protects=D-05 only a tray that can show an answer gets one; fails_when=a ticket from the old route is
    posted, or the new route's ticket is drafted."""
    legacy = await world.call("POST", "/api/agents/a1/ticket", json={
        "title": "I forgot my password", "description": "I cannot sign in to my laptop because I forgot my password and I need to reset it",
        "type": "bug", "tags": ["user-raised", "tray"], "endpoint_info": {"hostname": "LAPTOP1", "username": JDOE}})
    assert legacy.status_code == 200, legacy.text
    from tests.service_desk_tray_support import desk_pass
    await desk_pass(world)
    drafted = await world.stored(legacy.json()["ticket_id"])
    assert drafted["desk"]["phase"] == "drafted" and drafted["desk"]["draftReason"] == "no_tray_window"
    assert drafted["status"] == "open" and not [c for c in drafted["comments"] if c.get("visibility") == "requester"]
    assert (await world.list()).json()["tickets"] == []
    posted = await raised_and_answered(world)
    assert posted["desk"]["phase"] == "posted" and posted["status"] == "pending_customer"
