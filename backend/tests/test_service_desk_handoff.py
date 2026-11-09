"""The service desk hand-off, the requester notice and the gap rows (Phase 85, plan 85-12, DESK-02 / DESK-06).
Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py.

Value: protects=every desk escalation ends as one routed, noted, audited hand-off that tells the requester
plainly and tells staff why, pages no one and keeps the question for the gap list only when no article
covered it; fails_when=the queue rules are not applied or override a person, the requester notice names the
reason or appears for a stopped desk, an automated or legacy tray ticket, a second call adds a second note,
notice, ledger row or gap, a hand-off writes a notification or an on-call document or raises the priority, or
a gap row appears for any reason but no_article and not_english; no_claim=the callers of the hand-off
(85-04, 85-13 and later) and the knowledge-gap list (85-15).
"""
import os
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service_desk import DRAFT_REASONS, GAP_REASONS, HANDOFF_REASONS, gaps, handoff, messages, notify
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.service_desk_support import desk_indexes_without_ttl

NOW = datetime(2026, 11, 8, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
async def world(mongo_db, monkeypatch):  # noqa: F811
    import autonomous_ops.notify as ao_notify
    import ticket_notifications
    import tickets_config_mixin
    import tickets_service
    from autonomous_ops import ledger
    await ledger.ensure_indexes(mongo_db)
    await desk_indexes_without_ttl(mongo_db)
    for module in (tickets_service, tickets_config_mixin):
        monkeypatch.setattr(module, "get_database", lambda: mongo_db)
    # The normal "assigned to you" mail of the ticket queue is not what these tests look at.
    monkeypatch.setattr(ticket_notifications, "notify_assigned", AsyncMock())
    monkeypatch.setattr(ticket_notifications, "notify_status_changed", AsyncMock())
    paged = AsyncMock()
    monkeypatch.setattr(ao_notify, "notify", paged)
    mongo_db.paged = paged
    await mongo_db.ticket_queues.insert_one({"tenantId": "t1", "rules": [
        {"conditions": {"type": "bug"}, "assignee": "bugs@x.co"},
        {"conditions": {"type": "task"}, "assignee": "tech@x.co"}]})
    return mongo_db


def _ticket(number=1, *, tenant="t1", channel=None, via="portal", assignee=None, **extra):
    ticket = {"id": f"k{number}", "tenantId": tenant, "ticket_number": f"TKT-{number:04d}", "title": "VPN drops",
              "description": "The VPN drops every hour", "type": "task", "priority": "medium", "status": "open",
              "reporter": "Alice", "assignee": assignee, "raised_via": via, "comments": [], "history": [],
              "requester_channel": {"portal": True} if channel is None else channel, "escalated": False}
    ticket.update(extra)
    return ticket


async def _seed(db, **kwargs):
    ticket = _ticket(**kwargs)
    await db.tickets.insert_one(dict(ticket))
    return ticket


async def _stored(db, ticket):
    return await db.tickets.find_one({"id": ticket["id"], "tenantId": ticket["tenantId"]}, {"_id": 0})


async def _rows(db, tenant="t1"):
    return await db.autonomy_actions.find({"tenantId": tenant, "kind": "servicedesk"}, {"_id": 0}).to_list(50)


# ---------------------------------------------------------------- the code lists

def test_the_code_lists_equal_the_keys_of_the_message_tables():
    assert set(HANDOFF_REASONS) == set(messages.STAFF_REASON_LABELS)
    assert len(HANDOFF_REASONS) == len(set(HANDOFF_REASONS)) == 19
    assert set(DRAFT_REASONS) == set(messages.DRAFT_REASON_TEXT)
    assert len(DRAFT_REASONS) == len(set(DRAFT_REASONS)) == 8
    assert set(GAP_REASONS) < set(HANDOFF_REASONS)


# ---------------------------------------------------------------- the hand-off

async def test_a_hand_off_routes_the_ticket_notes_it_tells_the_requester_and_records_it(world):
    """protects=D-24: assignee from the queue rules, one staff note, one plain notice, the desk fields and one
    ledger row; fails_when=any of the five is missing or the notice text is not HANDOFF_NOTICE exactly."""
    db = world
    ticket = await _seed(db)
    assert await handoff.handoff(db, ticket, "no_article", now=NOW) is True
    stored = await _stored(db, ticket)
    assert stored["assignee"] == "tech@x.co"
    notes = [c for c in stored["comments"] if c["kind"] == "staff_note"]
    notices = [c for c in stored["comments"] if c["kind"] == "handoff_notice"]
    assert len(notes) == 1 and notes[0]["visibility"] == "staff"
    assert notes[0]["text"] == "Service desk: no article matched." and notes[0]["author"] == "Service desk"
    assert notes[0]["id"] == "sd-note-no_article-k1"
    assert len(notices) == 1 and notices[0]["visibility"] == "requester"
    assert notices[0]["text"] == messages.HANDOFF_NOTICE == "A person from IT will look at this."
    assert notices[0]["id"] == "sd-notice-no_article-k1"
    assert "article" not in notices[0]["text"].lower()
    assert stored["desk"]["phase"] == "handed_off" and stored["desk"]["lastReason"] == "no_article"
    assert stored["desk"]["draftWaiting"] is False
    rows = await _rows(db)
    assert len(rows) == 1
    assert (rows[0]["command"], rows[0]["reasonCode"], rows[0]["reasonText"]) == (
        "ticket_handoff", "no_article", "No article matched.")
    assert rows[0]["activityResult"] == messages.ACTIVITY["handoff_result"].format(number="TKT-0001")
    assert rows[0]["desk"]["ticketId"] == "k1"


async def test_the_queue_rule_follows_the_ticket_and_a_set_assignee_is_kept(world):
    db = world
    bug = await _seed(db, number=1, type="bug")
    taken = await _seed(db, number=2, assignee="ann@x.co")
    plain = await _seed(db, number=3, type="incident")
    for ticket in (bug, taken, plain):
        await handoff.handoff(db, ticket, "did_not_help", now=NOW)
    assert (await _stored(db, bug))["assignee"] == "bugs@x.co"
    assert (await _stored(db, taken))["assignee"] == "ann@x.co"
    assert (await _stored(db, plain))["assignee"] is None            # no rule matched: left for the queue


async def test_a_person_who_took_the_ticket_after_it_was_read_is_not_overridden(world):
    db = world
    ticket = await _seed(db)
    await db.tickets.update_one({"id": "k1"}, {"$set": {"assignee": "ann@x.co"}})       # the caller's copy is stale
    await handoff.handoff(db, ticket, "no_article", now=NOW)
    assert (await _stored(db, ticket))["assignee"] == "ann@x.co"


async def test_a_second_call_adds_nothing(world):
    """protects=idempotency: one note, one notice, one ledger row."""
    db = world
    ticket = await _seed(db)
    assert await handoff.handoff(db, ticket, "no_article", now=NOW) is True
    assert await handoff.handoff(db, ticket, "no_article", now=NOW) is False
    stored = await _stored(db, ticket)
    assert [c["kind"] for c in stored["comments"]] == ["staff_note", "handoff_notice"]
    assert len(await _rows(db)) == 1


async def test_a_second_reason_is_a_second_hand_off(world):
    db = world
    ticket = await _seed(db)
    await handoff.handoff(db, ticket, "no_article", now=NOW)
    await handoff.handoff(db, ticket, "did_not_help", now=NOW)
    stored = await _stored(db, ticket)
    assert [c["id"] for c in stored["comments"] if c["kind"] == "staff_note"] == [
        "sd-note-no_article-k1", "sd-note-did_not_help-k1"]
    assert stored["desk"]["lastReason"] == "did_not_help"
    assert len(await _rows(db)) == 2


async def test_the_requester_notice_never_names_the_reason_and_the_reason_stays_with_staff(world):
    """protects=T-85-42: for every reason, no requester-visible comment contains a staff label."""
    from service_desk import projection
    db = world
    for number, reason in enumerate(HANDOFF_REASONS, start=1):
        ticket = await _seed(db, number=number)
        await handoff.handoff(db, ticket, reason, now=NOW)
        stored = await _stored(db, ticket)
        shown = " ".join(item["text"] for item in projection.requester_items(stored))
        assert messages.STAFF_REASON_LABELS[reason] not in shown.lower()
        assert messages.sentence(messages.STAFF_REASON_LABELS[reason]) not in shown
        assert any(c["text"] == f"Service desk: {messages.STAFF_REASON_LABELS[reason]}." and c["visibility"] == "staff"
                   for c in stored["comments"])


async def test_a_stopped_desk_a_tray_without_my_tickets_and_an_automated_ticket_get_no_notice(world):
    db = world
    stopped = await _seed(db, number=1)
    legacy = await _seed(db, number=2, channel={"tray": True, "myTickets": False}, via="tray")
    robot = await _seed(db, number=3, channel=None, via="automation")
    robot["requester_channel"] = None
    await db.tickets.update_one({"id": "k3"}, {"$set": {"requester_channel": None}})
    await handoff.handoff(db, stopped, "desk_stopped", now=NOW)
    await handoff.handoff(db, legacy, "no_article", now=NOW)
    await handoff.handoff(db, robot, "no_article", now=NOW)
    for ticket in (stopped, legacy, robot):
        stored = await _stored(db, ticket)
        assert [c["kind"] for c in stored["comments"]] == ["staff_note"], ticket["id"]
        assert stored["desk"]["phase"] == "handed_off"
        assert stored["assignee"] == "tech@x.co"                 # still routed to a person
    assert len(await _rows(db)) == 3


async def test_a_tray_requester_with_my_tickets_and_the_notify_flag(world):
    db = world
    tray = await _seed(db, number=1, channel={"tray": True, "myTickets": True}, via="tray")
    quiet = await _seed(db, number=2)
    await handoff.handoff(db, tray, "no_article", now=NOW)
    await handoff.handoff(db, quiet, "no_article", now=NOW, notify_requester=False)
    assert [c["kind"] for c in (await _stored(db, tray))["comments"]] == ["staff_note", "handoff_notice"]
    assert [c["kind"] for c in (await _stored(db, quiet))["comments"]] == ["staff_note"]


async def test_a_hand_off_pages_no_one_and_changes_no_priority(world):
    """protects=D-22 / T-85-43 / PROH-85-07: no notification, no on-call document, no Autonomous Ops notify call,
    priority and escalated unchanged."""
    db = world
    ticket = await _seed(db, priority="low")
    for reason in ("no_article", "critical_priority", "security_topic"):
        await handoff.handoff(db, ticket, reason, now=NOW)
    stored = await _stored(db, ticket)
    assert (stored["priority"], stored["escalated"]) == ("low", False)
    assert await db.notifications.count_documents({}) == 0
    assert await db.oncall_outbox.count_documents({}) == 0
    assert db.paged.await_count == 0


async def test_an_unknown_reason_or_a_ticket_without_ids_is_refused(world):
    ticket = await _seed(world)
    with pytest.raises(ValueError):
        await handoff.handoff(world, ticket, "because_i_said_so")
    with pytest.raises(ValueError):
        await handoff.handoff(world, {"title": "no ids"}, "no_article")
    assert await world.tickets.count_documents({"comments.0": {"$exists": True}}) == 0


async def test_a_failing_write_does_not_stop_the_rest(world, monkeypatch):
    """protects=the ticket must reach a person: a queue rule that fails to apply still leaves the note, the
    notice and the ledger row."""
    import tickets_service
    monkeypatch.setattr(tickets_service.tickets_service, "auto_assign", AsyncMock(side_effect=RuntimeError("down")))
    ticket = await _seed(world)
    assert await handoff.handoff(world, ticket, "no_article", now=NOW) is True
    stored = await _stored(world, ticket)
    assert [c["kind"] for c in stored["comments"]] == ["staff_note", "handoff_notice"]
    assert stored["desk"]["phase"] == "handed_off" and len(await _rows(world)) == 1


async def test_another_tenants_ticket_is_never_touched(world):
    other = await _seed(world, number=9, tenant="t2")
    mine = dict(other, tenantId="t1")                           # a caller bug: right id, wrong tenant
    assert await handoff.handoff(world, mine, "no_article", now=NOW) is False
    assert (await _stored(world, other))["comments"] == []


# ---------------------------------------------------------------- the requester notice

async def test_a_portal_requester_gets_one_tagged_in_app_notice_with_no_preview(world):
    """protects=D-12 / D-33: stored for the reporter only, no channel, text is the ticket number alone."""
    db = world
    ticket = _ticket(title="Secret salary question", description="private details here", reporter="Alice")
    assert await notify.requester_notice(db, ticket, event="answer_posted") is True
    docs = await db.notifications.find({}, {"_id": 0}).to_list(10)
    assert len(docs) == 1
    note = docs[0]
    assert note["metadata"]["recipient"] == "alice" and note["metadata"]["ticket_id"] == "k1"
    assert note["metadata"]["event"] == "answer_posted" and note["tenantId"] == "t1"
    assert note["title"] == "Your ticket TKT-0001 has an answer"      # send_alert stores the title, not the text
    assert note["channels"] == {}
    blob = repr(note)
    assert "salary" not in blob and "private" not in blob


async def test_the_notice_can_carry_the_callers_generic_text(world):
    ticket = _ticket()
    await notify.requester_notice(world, ticket, event="handoff", title="Update on TKT-0001",
                                  message=messages.HANDOFF_NOTICE)
    note = await world.notifications.find_one({}, {"_id": 0})
    assert note["title"] == "Update on TKT-0001"


async def test_a_tray_or_automated_ticket_or_one_without_a_reporter_gets_no_notice(world):
    for ticket in (_ticket(channel={"tray": True, "myTickets": True}), _ticket(channel={}),
                   _ticket(requester_channel=None), _ticket(reporter=""), _ticket(reporter=None)):
        assert await notify.requester_notice(world, ticket, event="x") is False
    assert await world.notifications.count_documents({}) == 0


async def test_the_notice_never_raises(world, monkeypatch):
    import notification_service
    monkeypatch.setattr(notification_service.NotificationService, "send_alert",
                        AsyncMock(side_effect=RuntimeError("down")))
    assert await notify.requester_notice(world, _ticket(), event="x") is False


# ---------------------------------------------------------------- the gap rows

async def _gaps(db, tenant="t1"):
    return await db.service_desk_gaps.find({"tenantId": tenant}, {"_id": 0}).to_list(50)


async def test_only_no_article_and_not_english_leave_a_gap_row(world):
    """protects=D-26: a gap exists exactly for the two gap reasons; fails_when=any other reason writes one."""
    db = world
    seen = set()
    for number, reason in enumerate(HANDOFF_REASONS, start=1):
        ticket = await _seed(db, number=number)
        await handoff.handoff(db, ticket, reason, now=NOW)
        if await db.service_desk_gaps.count_documents({"ticketId": ticket["id"]}):
            seen.add(reason)
    assert seen == {"no_article", "not_english"} == set(GAP_REASONS)


async def test_a_gap_row_holds_the_cleaned_question_cut_to_300_characters(world):
    db = world
    long_title = "How do I connect? See https://intranet.example.com/vpn or mail it@example.com " + "x" * 400
    ticket = await _seed(db, title=long_title)
    await handoff.handoff(db, ticket, "no_article", now=NOW)
    (row,) = await _gaps(db)
    assert row["reason"] == "no_article" and row["status"] == "open" and row["id"].startswith("SDG-")
    assert (row["ticketId"], row["ticketNumber"], row["tenantId"]) == ("k1", "TKT-0001", "t1")
    assert len(row["text"]) <= 300 and row["text"].startswith("How do I connect?")
    assert "http" not in row["text"] and "@" not in row["text"]
    assert isinstance(row["createdAt"], datetime)


async def test_the_caller_can_hand_over_the_question_and_not_english_is_kept(world):
    db = world
    ticket = await _seed(db, title="Hola", description="No puedo entrar")
    await handoff.handoff(db, ticket, "not_english", now=NOW, question="Hola. No puedo entrar")
    (row,) = await _gaps(db)
    assert (row["reason"], row["text"]) == ("not_english", "Hola. No puedo entrar")


async def test_a_second_hand_off_for_the_same_ticket_and_reason_writes_no_second_gap(world):
    db = world
    ticket = await _seed(db)
    await handoff.handoff(db, ticket, "no_article", now=NOW)
    await handoff.handoff(db, ticket, "no_article", now=NOW)
    assert await gaps.record(db, "t1", ticket_id="k1", ticket_number="TKT-0001", text="again", reason="no_article",
                             now=NOW) is False
    assert len(await _gaps(db)) == 1
    await handoff.handoff(db, ticket, "not_english", now=NOW)           # another reason is another row
    assert sorted(g["reason"] for g in await _gaps(db)) == ["no_article", "not_english"]


async def test_record_refuses_a_reason_that_is_not_a_gap_reason(world):
    for reason in ("fulfilment_request", "security_topic", "busy", ""):
        with pytest.raises(ValueError):
            await gaps.record(world, "t1", ticket_id="k1", ticket_number="TKT-0001", text="x", reason=reason, now=NOW)
    assert await _gaps(world) == []


async def test_an_empty_question_leaves_no_row_but_the_hand_off_still_happens(world):
    ticket = await _seed(world, title="")
    assert await handoff.handoff(world, ticket, "no_article", now=NOW) is True
    assert await _gaps(world) == []
    assert len(await _rows(world)) == 1


async def test_a_gap_row_is_kept_per_tenant(world):
    mine = await _seed(world, number=1)
    other = await _seed(world, number=2, tenant="t2")
    await handoff.handoff(world, mine, "no_article", now=NOW)
    await handoff.handoff(world, other, "no_article", now=NOW)
    assert [g["ticketId"] for g in await _gaps(world, "t1")] == ["k1"]
    assert [g["ticketId"] for g in await _gaps(world, "t2")] == ["k2"]
