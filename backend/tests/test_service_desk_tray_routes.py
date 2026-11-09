"""The tray routes of the service desk (Phase 85, plan 85-19, DESK-01, decisions D-05 to D-07, D-11, D-14, D-34).
Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py; the agent-key check is
the production code with a signed agent token per request; the local model is a stand-in.

Value: protects=the tray raises tickets that the desk may post to, its list shows each Windows user only their
own tickets from this computer and only what a requester may read, and confirm, help and article reads act on
the caller's own tickets only; fails_when=a draft, a staff note, a hand-off reason or a withdrawn answer's text
reaches the list, another user, another computer or another tenant sees or acts on a ticket, a body field decides
who raised a ticket, or an old tray's ticket is posted to; no_claim=how the window looks (UI-SPEC section 8, the
user's step on Windows) and the script's own behaviour (test_service_desk_tray_static.py).
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service_desk import messages, store, tray_contract
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.service_desk_portal_support import ANSWER
from tests.service_desk_tray_support import (CREATE, JDOE, build_tray_world, create_body, raised_and_answered,
                                             say, seed_ticket)

DRAFT = "internal-only: the admin password is hunter2"
STAFF_NOTE = "Service desk: security topic."


@pytest.fixture
async def world(mongo_db, monkeypatch):  # noqa: F811
    return await build_tray_world(mongo_db, monkeypatch)


async def _listed(world, agent="a1", user=JDOE):
    response = await world.list(agent, user)
    assert response.status_code == 200, response.text
    return response.json()["tickets"]


# ---------------------------------------------------------------- create

async def test_create_marks_the_ticket_as_a_tray_ticket_by_route_identity(world):
    """protects=D-05 a ticket from the new tray is a tray ticket of this agent that can show an answer, with the
    created text the tray prints; fails_when=the channel, the reporter, the tags or the response differ."""
    response = await world.create("a1", template="report_issue")
    assert response.status_code == 200, response.text
    body = response.json()
    stored = await world.stored(body["ticket_id"])
    assert body == {"ticket_id": stored["id"], "ticket_number": stored["ticket_number"],
                    "message": messages.TRAY_CREATED.format(number=stored["ticket_number"])}
    assert stored["raised_via"] == "tray" and stored["reporter"] == "a1" and stored["agent_id"] == "a1"
    assert stored["requester_channel"] == {"portal": False, "tray": True, "myTickets": True, "windowsUser": JDOE,
                                           "template": "report_issue"}
    assert stored["tags"] == ["user-raised", "tray"] and stored["tenantId"] == "t1"
    assert stored["endpoint_info"]["username"] == JDOE
    assert await store.jobs(world.db).count_documents({"ticketId": stored["id"]}) == 1


async def test_a_tray_without_the_my_tickets_claim_is_marked_so(world):
    """protects=D-05 a tray that cannot show an answer never gets one; fails_when=myTickets is True without the
    claim in client.features."""
    for features in ((), ("something_else",)):
        response = await world.create("a1", features=features)
        stored = await world.stored(response.json()["ticket_id"])
        assert stored["requester_channel"]["myTickets"] is False


async def test_a_body_field_cannot_decide_who_raised_the_ticket(world):
    """protects=T-85-33 the route, not the body, decides; fails_when=a claimed raised_via, channel, reporter, tags
    or tenant is stored."""
    response = await world.create("a1", raised_via="portal", reporter="boss@x.co", tenantId="t2", tags=["agent-raised"],
                                  requester_channel={"portal": True, "windowsUser": "someone-else"},
                                  agent_id="b1")
    stored = await world.stored(response.json()["ticket_id"])
    assert stored["raised_via"] == "tray" and stored["reporter"] == "a1" and stored["tenantId"] == "t1"
    assert stored["tags"] == ["user-raised", "tray"] and stored["agent_id"] == "a1"
    assert stored["requester_channel"]["portal"] is False and stored["requester_channel"]["windowsUser"] == JDOE


@pytest.mark.parametrize("change", [
    {"template": "teleport"},
    {"title": "x" * 201},
    {"title": ""},
    {"type": "wish"},
    {"priority": "urgent-ish"},
    {"endpoint_info": {"hostname": "LAPTOP1"}},
    {"endpoint_info": {"username": "   "}},
    {"endpoint_info": {"username": "u" * 257}},
    {"endpoint_info": None},
    {"description": "d" * 5001},
], ids=lambda c: next(iter(c)) + "-" + str(len(json.dumps(c))))
async def test_a_malformed_create_is_refused_and_stores_nothing(world, change):
    """protects=the create body is validated at the boundary; fails_when=a bad body is accepted or stores a ticket."""
    body = {**create_body(), **change}
    response = await world.call("POST", CREATE.format(agent="a1"), json=body)
    assert response.status_code == 422, response.text
    assert await world.db.tickets.count_documents({}) == 0


async def test_the_longest_allowed_title_and_a_missing_template_are_accepted(world):
    body = create_body()
    del body["template"]
    body["title"] = "t" * tray_contract.TITLE_MAX
    response = await world.call("POST", CREATE.format(agent="a1"), json=body)
    assert response.status_code == 200, response.text
    stored = await world.stored(response.json()["ticket_id"])
    assert stored["requester_channel"]["template"] == "custom"


@pytest.mark.real_agent_capabilities
async def test_create_needs_the_agents_own_token_and_the_capability(world):
    """protects=T-85-72 a token names one agent; fails_when=another agent's token, the registration key, no
    credentials or a tenant without the capability can create."""
    path = CREATE.format(agent="a1")
    assert (await world.create("a1", as_agent="a2")).status_code == 403          # a2's token on a1's path
    await world.db.tenants.update_one({"id": "t1"}, {"$set": {"registrationKey": "reg-key"}})
    assert (await world.call("POST", path, json=create_body(), headers={"X-Tenant-Key": "reg-key"})).status_code == 403
    assert (await world.call("POST", path, json=create_body(), headers={})).status_code == 401
    await world.db.tenants.update_one({"id": "t1"}, {"$set": {"agentCapabilities": ["asset_inventory"]}})
    assert (await world.create("a1")).status_code == 403
    assert await world.db.tickets.count_documents({}) == 0


async def test_an_agent_that_is_not_enrolled_in_the_tenant_gets_404(world):
    """protects=the agent is found inside the token's tenant; fails_when=a name of another tenant's agent works."""
    path = CREATE.format(agent="ghost")
    response = await world.call("POST", path, agent="a1", json=create_body())
    assert response.status_code in (403, 404)
    assert await world.db.tickets.count_documents({}) == 0


# ---------------------------------------------------------------- list: what the requester may see

async def test_the_list_holds_only_what_a_requester_may_read(world):
    """protects=T-85-71 / PROH-85-05 the enforced boundary; fails_when=the serialized list contains a draft, a
    staff note, a hand-off reason or a staff-only comment, or an entry is missing or out of order."""
    ticket = await seed_ticket(world)
    at = datetime.now(timezone.utc)
    ai = {"actionId": "act-1", "citations": [{"articleId": "kb-pw", "title": "Reset your own password",
                                              "contentHash": "h"}], "state": "posted"}
    await say(world, ticket, "sd-act-1", "ai_answer", ANSWER, author="Service desk", ai=ai, at=at)
    await say(world, ticket, "sd-act-2", "ai_draft", DRAFT, visibility="staff", ai={"state": "draft", "actionId": "x",
              "citations": [{"articleId": "kb-vpn", "title": "Connect to the VPN"}]}, at=at + timedelta(seconds=1))
    await say(world, ticket, "sd-note", "staff_note", STAFF_NOTE, visibility="staff", at=at + timedelta(seconds=2))
    await say(world, ticket, "c-staff", None, "Restarted your profile, try again", author="bob@x.co",
              at=at + timedelta(seconds=3))
    await say(world, ticket, "c-private", None, "internal: password is hunter2", author="bob@x.co", visibility="staff",
              at=at + timedelta(seconds=4))
    await say(world, ticket, "sd-help-1", "requester_reply", "still broken", author="tray:a1",
              at=at + timedelta(seconds=5))
    await say(world, ticket, "sd-notice-1", "handoff_notice", messages.HANDOFF_NOTICE, at=at + timedelta(seconds=6))
    await world.db.tickets.update_one({"id": ticket["id"]}, {"$set": {"desk": {
        "phase": "handed_off", "lastReason": "security_topic", "draftReason": "mode_drafts", "actionId": "act-1"}}})

    response = await world.list()
    raw_text = response.text
    for secret in (DRAFT, "hunter2", STAFF_NOTE, "security", "mode_drafts", "Connect to the VPN"):
        assert secret not in raw_text, secret
    [shown] = response.json()["tickets"]
    assert set(shown) == set(tray_contract.TICKET_FIELDS)
    assert [e["kind"] for e in shown["entries"]] == ["answer", "reply", "you", "notice"]
    assert all(set(e) == set(tray_contract.ENTRY_FIELDS) for e in shown["entries"])
    answer, reply, you, notice = shown["entries"]
    assert answer["heading"] == messages.TRAY_HEADINGS["answer"] and answer["text"] == ANSWER
    assert answer["citations"] == [{"articleId": "kb-pw", "title": "Reset your own password"}]
    assert reply["heading"] == messages.TRAY_HEADINGS["reply"] and reply["text"] == "Restarted your profile, try again"
    assert you["heading"] == messages.TRAY_HEADINGS["you"] and you["text"] == "still broken"
    assert notice["text"] == messages.HANDOFF_NOTICE
    assert shown["answerIds"] == ["sd-act-1"]
    assert shown["id"] == ticket["id"] and shown["number"] == ticket["ticket_number"] and shown["title"] == "VPN is down"
    assert shown["statusText"] == messages.TRAY_STATUS_TEXT["with_it"]
    assert shown["reasonLine"] == messages.TRAY_REASON_LINES["with_it"]
    assert shown["canConfirm"] is False and shown["canHelp"] is False


async def test_a_withdrawn_answer_reads_as_the_withdrawal_notice_and_is_not_an_answer_id(world):
    """protects=D-25 a withdrawn answer's text and citations never reach the tray; fails_when=its text, its
    citations or its id appear, or the notice appears twice."""
    ticket = await seed_ticket(world)
    at = datetime.now(timezone.utc)
    text = "Open the sign-in page. The withdrawn text must not appear."
    ai = {"actionId": "act-1", "state": "withdrawn", "withdrawnAt": (at + timedelta(minutes=5)).isoformat(),
          "citations": [{"articleId": "kb-pw", "title": "Reset your own password"}]}
    await say(world, ticket, "sd-act-1", "ai_answer", text, ai=ai, at=at)
    await say(world, ticket, "sd-withdrawn-act-1", "withdrawn_notice", messages.WITHDRAWN_NOTICE,
              at=at + timedelta(minutes=5))
    await world.db.tickets.update_one({"id": ticket["id"]}, {"$set": {"status": "open", "desk": {"phase": "withdrawn"}}})
    response = await world.list()
    assert "must not appear" not in response.text and "Reset your own password" not in response.text
    [shown] = response.json()["tickets"]
    assert shown["entries"] == [{"kind": "withdrawn", "at": ai["withdrawnAt"], "heading": "",
                                 "text": messages.WITHDRAWN_NOTICE, "citations": []}]
    assert shown["answerIds"] == []
    assert shown["reasonLine"] == messages.TRAY_REASON_LINES["withdrawn"] and shown["canConfirm"] is False


async def test_the_answer_buttons_follow_the_desk_phase_and_the_status(world):
    """protects=D-07 the buttons are on only while an answer waits on the requester; fails_when=canConfirm is
    True in any other state or the status words differ."""
    cases = [("posted", "pending_customer", True, "answer_ready"), ("sent", "pending_customer", True, "answer_ready"),
             ("posted", "open", False, "received"), ("confirmed", "resolved", False, "resolved"),
             ("handed_off", "open", False, "with_it"), ("posted", "closed", False, "closed"),
             ("queued", "open", False, "received"), ("draft", "open", False, "received"),
             (None, "pending_customer", False, "waiting_for_you")]
    for phase, status, confirm, text_key in cases:
        ticket = await seed_ticket(world, title=f"{phase}-{status}")
        await world.db.tickets.update_one({"id": ticket["id"]}, {"$set": {"status": status, "desk": {"phase": phase}}})
    shown = {t["title"]: t for t in await _listed(world)}
    for phase, status, confirm, text_key in cases:
        item = shown[f"{phase}-{status}"]
        assert item["canConfirm"] is confirm and item["canHelp"] is confirm, (phase, status)
        assert item["statusText"] == messages.TRAY_STATUS_TEXT[text_key], (phase, status)
        assert item["status"] == status
    assert shown["confirmed-resolved"]["reasonLine"] == messages.TRAY_REASON_LINES["resolved"]
    assert shown["posted-pending_customer"]["reasonLine"] == ""


async def test_the_list_answers_with_the_display_strings_and_the_reported_user(world):
    response = await world.list(user=" JDoe ")
    body = response.json()
    assert body == {"tickets": [], "user": "JDoe", "display": {
        "footnote": messages.TRAY_FOOTNOTE.format(user="JDoe"), "footer": messages.FOOTER, "empty": messages.TRAY_EMPTY}}
    assert "private" not in body["display"]["footnote"].lower()


# ---------------------------------------------------------------- list: whose tickets

async def test_a_user_sees_only_their_own_tickets_from_this_computer(world):
    """protects=D-06 / T-85-72 the scope is this tenant, this agent and this Windows user; fails_when=another
    Windows user, another computer of the tenant, another tenant, an old tray's ticket or an old ticket is listed."""
    mine = await seed_ticket(world, title="mine")
    await seed_ticket(world, user="other", title="another user")
    await seed_ticket(world, agent="a2", title="another computer")
    await seed_ticket(world, tenant="t2", agent="b1", title="another tenant")
    await seed_ticket(world, tenant="t2", agent="a1", title="same agent id, another tenant")
    await seed_ticket(world, my_tickets=False, title="old tray")
    await seed_ticket(world, title="too old", age_days=61)
    other = await world.db.tickets.insert_one({"id": "portal-1", "tenantId": "t1", "agent_id": "a1", "raised_via": "portal",
                                               "requester_channel": {"portal": True, "windowsUser": JDOE}, "title": "portal",
                                               "created_at": datetime.now(timezone.utc).isoformat(), "comments": []})
    assert other.acknowledged
    assert [t["id"] for t in await _listed(world)] == [mine["id"]]
    assert await _listed(world, user="nobody") == []
    assert [t["title"] for t in await _listed(world, user="other")] == ["another user"]
    assert [t["title"] for t in await _listed(world, "a2")] == ["another computer"]    # each computer lists its own
    assert [t["title"] for t in await _listed(world, "b1")] == ["another tenant"]
    assert [t["title"] for t in await _listed(world, user="JDOE")] == ["mine"]   # the match ignores case


async def test_the_list_is_the_20_newest_tickets_of_the_last_60_days(world):
    """protects=T-85-75 a bounded list, newest first; fails_when=more than 20, oldest first or a 59-day ticket missing."""
    for n in range(25):
        await seed_ticket(world, title=f"t{n:02d}", age_days=(24 - n) / 24.0)
    await seed_ticket(world, title="old but inside", age_days=59)
    titles = [t["title"] for t in await _listed(world)]
    assert titles == [f"t{n:02d}" for n in range(24, 4, -1)]
    assert len(titles) == tray_contract.LIST_LIMIT and "old but inside" not in titles     # cut by the limit, not the date


async def test_another_agent_cannot_list_this_computers_tickets(world):
    """protects=T-85-72 the token binds the path agent; fails_when=a2's token lists a1's tickets."""
    await seed_ticket(world)
    response = await world.call("GET", CREATE.format(agent="a1"), agent="a2", params={"user": JDOE})
    assert response.status_code == 403
    assert (await world.call("GET", CREATE.format(agent="a1"), headers={})).status_code == 401
    assert (await world.call("GET", CREATE.format(agent="a1"), params={"user": "  "})).status_code == 422
    assert (await world.call("GET", CREATE.format(agent="a1"))).status_code == 422


# ---------------------------------------------------------------- the pipeline posts only to a tray that can read

async def test_a_new_tray_ticket_is_posted_and_the_tray_reads_the_answer(world):
    """protects=D-05 the whole path: create, one desk pass, list; fails_when=the answer is a draft, or the list
    does not carry the answer with its citation and the buttons."""
    ticket = await raised_and_answered(world)
    assert ticket["status"] == "pending_customer" and ticket["desk"]["phase"] == "posted"
    [shown] = await _listed(world)
    [answer] = shown["entries"]
    assert answer["kind"] == "answer" and answer["text"] == ANSWER and answer["citations"][0]["articleId"] == "kb-pw"
    assert shown["answerIds"] == [ticket["desk"]["commentId"]]
    assert shown["canConfirm"] is True and shown["statusText"] == messages.TRAY_STATUS_TEXT["answer_ready"]


async def test_a_ticket_from_a_tray_without_the_claim_stays_a_draft(world):
    """protects=D-05 an old tray never gets a posted answer; fails_when=it is posted, or the draft shows in the list."""
    ticket = await raised_and_answered(world, features=())
    assert ticket["desk"]["phase"] == "drafted" and ticket["desk"]["draftReason"] == "no_tray_window"
    response = await world.list()
    assert response.json()["tickets"] == []                                     # not myTickets: not listed at all
    assert ANSWER not in response.text


# ---------------------------------------------------------------- rate limits

async def test_writes_are_limited_to_10_a_minute_and_reads_to_30_per_agent(world):
    """protects=T-85-75 a polling or looping tray cannot flood the server, and one agent's use does not use up
    another's; fails_when=the 11th create or the 31st list in a minute is answered, or a2 is limited by a1."""
    for _ in range(10):
        assert (await world.create("a1")).status_code == 200
    assert (await world.create("a1")).status_code == 429
    assert (await world.create("a2")).status_code == 200
    for _ in range(30):
        assert (await world.list("a1")).status_code == 200
    assert (await world.list("a1")).status_code == 429
    assert (await world.list("a2")).status_code == 200
