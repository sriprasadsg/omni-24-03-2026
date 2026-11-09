"""The knowledge-gap list of the service desk (Phase 85, plan 85-15, DESK-06, decisions D-26, D-27). Real MongoDB
(skips without one) through the throwaway database of tests/_mongo_test_db.py.

Value: protects=authors see the questions the desk could not answer, grouped by plain text similarity with no
model, only for their own tenant and only with both the ticket and the Knowledge Base permission; fails_when=a
group is wrong or its order changes between calls, a dismissed or written group is listed, another tenant's rows
or group ids are reachable, or a Knowledge Base editor without ticket access reads the list; no_claim=how the
rows are written (test_service_desk_handoff.py) and the screen (85-16).
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from service_desk import gaps, messages, store
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.service_desk_knowledge_support import OVER, KbApp


@pytest.fixture
async def kb(mongo_db, monkeypatch):  # noqa: F811
    await store.ensure_indexes(mongo_db)
    return KbApp(mongo_db, monkeypatch)


GAPS_PATH = "/api/knowledge/helpdesk/gaps"
ARTICLES_PATH = "/api/knowledge/helpdesk/articles"


async def _gap(db, text, ticket, *, minutes_ago=0, reason="no_article", tenant="t1", now=None):
    """One gap row as the hand-off writes it, ``minutes_ago`` before ``now`` (the test's own clock)."""
    stamp = (now or datetime.now(timezone.utc)) - timedelta(minutes=minutes_ago)
    assert await gaps.record(db, tenant, ticket_id=ticket, ticket_number=f"TKT-{ticket}", text=text,
                             reason=reason, now=stamp)


async def _vpn_world(db, now=None):
    await _gap(db, "vpn keeps disconnecting", "T1", minutes_ago=30, now=now)
    await _gap(db, "VPN keeps disconnecting!", "T2", minutes_ago=20, now=now)
    await _gap(db, "vpn disconnects every hour", "T3", minutes_ago=10, now=now)
    await _gap(db, "how do I order a new monitor", "T4", minutes_ago=5, now=now)
    await _gap(db, "mi impresora no funciona", "T5", reason="not_english", minutes_ago=4, now=now)
    await _gap(db, "mon imprimante ne marche pas", "T6", reason="not_english", minutes_ago=3, now=now)


async def _row(db, ticket, reason="no_article"):
    return await db.service_desk_gaps.find_one({"ticketId": ticket, "reason": reason})


def _fake_rows(count, *, text="question"):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [{"id": f"SDG-{i:03d}", "text": f"{text} {i}", "createdAt": base + timedelta(minutes=i),
             "ticketId": f"T{i}", "ticketNumber": f"TKT-{i}"} for i in range(count)]


async def test_questions_are_grouped_by_text_and_ordered_by_how_often_they_were_asked(kb):
    """protects=D-26 grouping with no model; fails_when=the three VPN questions are not one group of three, the
    monitor question is not its own group of one, the order is not count first, the group is not named by the
    newest question, the other-language rows are listed instead of counted, or the group id is not the oldest id."""
    await _vpn_world(kb.db)
    resp = await kb.call("GET", GAPS_PATH)
    assert resp.status_code == 200
    body = resp.json()
    assert [g["count"] for g in body["groups"]] == [3, 1]
    vpn, monitor = body["groups"]
    assert vpn["question"] == "vpn disconnects every hour" and vpn["status"] == "open"
    assert vpn["id"] == (await _row(kb.db, "T1"))["id"]
    assert [t["number"] for t in vpn["tickets"]] == ["TKT-T3", "TKT-T2", "TKT-T1"]
    assert [t["id"] for t in vpn["tickets"]] == ["T3", "T2", "T1"]
    assert vpn["lastAskedAt"].startswith((await _row(kb.db, "T3"))["createdAt"].strftime("%Y-%m-%dT%H:%M:%S"))
    assert monitor["question"] == "how do I order a new monitor" and monitor["count"] == 1
    assert body["otherLanguageCount"] == 2 and body["dismissedCount"] == 0 and body["deskOff"] is False
    assert all("impresora" not in g["question"] and "imprimante" not in g["question"] for g in body["groups"])


async def test_with_no_gap_rows_the_list_is_empty(kb):
    """protects=D-26 empty; fails_when=a tenant with no rows gets a group or a count."""
    body = (await kb.call("GET", GAPS_PATH)).json()
    assert body["groups"] == [] and body["otherLanguageCount"] == 0 and body["dismissedCount"] == 0


def test_a_pair_scoring_exactly_the_threshold_joins_one_group_and_a_lower_pair_does_not():
    """protects=D-26 adjacency, a cosine of 0.6 groups; fails_when=0.6 splits or 0.59 groups."""
    rows = _fake_rows(2)
    at = lambda value: (lambda texts: [[1.0, value], [value, 1.0]])           # noqa: E731
    assert [len(g) for g in gaps.group(rows, similarity=at(0.6))] == [2]
    assert [len(g) for g in gaps.group(rows, similarity=at(0.59))] == [1, 1]
    assert gaps.GROUP_THRESHOLD == 0.6


def test_identical_questions_always_group_even_when_no_word_is_left_to_compare():
    """protects=D-26 identical questions group; fails_when=a question made only of everyday words groups apart
    from its own copy, or different questions of that kind group together."""
    rows = _fake_rows(3)
    for row, text in zip(rows, ("I need help please", "I need help please", "please help me")):
        row["text"] = text
    groups = gaps.group(rows)
    assert sorted(len(g) for g in groups) == [1, 2]
    assert {r["text"] for r in next(g for g in groups if len(g) == 2)} == {"I need help please"}


def test_grouping_does_not_depend_on_the_order_the_rows_arrive_in():
    """protects=D-26 deterministic; fails_when=shuffled input gives other groups or other group ids."""
    rows = _fake_rows(6)
    for row, text in zip(rows, ("vpn keeps dropping", "vpn dropping again", "vpn drops", "printer jam", "printer jam again", "new laptop")):
        row["text"] = text
    first = [(gaps.oldest_id(g), [r["id"] for r in g]) for g in gaps.group(rows)]
    for ordering in (rows[::-1], rows[3:] + rows[:3], rows[1::2] + rows[::2]):
        assert [(gaps.oldest_id(g), [r["id"] for r in g]) for g in gaps.group(list(ordering))] == first


async def test_groups_are_ordered_by_count_then_newest_then_id_and_the_same_every_call(kb):
    """protects=D-26 ordering; fails_when=an equal-count group is not ordered newest first, an equal-time pair is
    not ordered by id, or two calls disagree."""
    now = datetime.now(timezone.utc)
    await _gap(kb.db, "mfa app lost on phone", "A1", minutes_ago=50, now=now)
    await _gap(kb.db, "mfa app lost on phone", "A2", minutes_ago=49, now=now)
    await _gap(kb.db, "projector in room nine", "B1", minutes_ago=1, now=now)
    await _gap(kb.db, "badge reader broken door", "C1", minutes_ago=2, now=now)
    await _gap(kb.db, "headset microphone crackles", "D1", minutes_ago=2, now=now)       # same instant as C1
    first = (await kb.call("GET", GAPS_PATH)).json()["groups"]
    assert [g["count"] for g in first] == [2, 1, 1, 1]
    assert first[1]["question"] == "projector in room nine"
    tied = [g["id"] for g in first[2:]]
    assert tied == sorted(tied)
    for _ in range(3):
        assert [g["id"] for g in (await kb.call("GET", GAPS_PATH)).json()["groups"]] == [g["id"] for g in first]


async def test_only_open_no_article_rows_of_the_last_90_days_for_this_tenant_are_listed(kb):
    """protects=D-26 / T-85-56 scope; fails_when=an old, written, dismissed, foreign or other-language row is listed."""
    now = datetime.now(timezone.utc)
    await _gap(kb.db, "fresh question about toner", "N1", minutes_ago=60, now=now)
    await _gap(kb.db, "old question about toner supply", "N2", minutes_ago=100 * 24 * 60, now=now)
    await _gap(kb.db, "written question about badges", "N3", now=now)
    await _gap(kb.db, "dismissed question about ladders", "N4", now=now)
    await _gap(kb.db, "foreign question about toner", "N5", tenant="t2", now=now)
    await kb.db.service_desk_gaps.update_one({"ticketId": "N3"}, {"$set": {"status": "written"}})
    await kb.db.service_desk_gaps.update_one({"ticketId": "N4"}, {"$set": {"status": "dismissed"}})
    body = (await kb.call("GET", GAPS_PATH)).json()
    assert [g["question"] for g in body["groups"]] == ["fresh question about toner"]
    assert body["dismissedCount"] == 1 and body["otherLanguageCount"] == 0


async def test_a_question_is_cut_to_200_characters_and_at_most_500_rows_are_read(kb):
    """protects=D-26 the caps; fails_when=a long question is shown whole, or more than the newest 500 rows count."""
    now = datetime.now(timezone.utc)
    base = {"tenantId": "t1", "reason": "no_article", "status": "open", "ticketNumber": "TKT"}
    rows = [{**base, "id": f"SDG-bulk{i:04d}", "ticketId": f"bulk{i}", "text": f"zzq{i}x yyw{i}k",
             "createdAt": now - timedelta(seconds=600 - i)} for i in range(510)]
    rows.append({**base, "id": "SDG-long", "ticketId": "long", "text": "wordy " * 50, "createdAt": now})
    await kb.db.service_desk_gaps.insert_many(rows)
    groups = (await kb.call("GET", GAPS_PATH)).json()["groups"]
    assert sum(g["count"] for g in groups) == 500
    assert len(next(g for g in groups if g["id"] == "SDG-long")["question"]) == 200
    listed = {t["id"] for g in groups for t in g["tickets"]}
    assert "bulk0" not in listed and "bulk509" in listed


async def test_dismiss_hides_a_group_and_restore_brings_it_back(kb):
    """protects=R6 / R7 dismiss and restore act on every member; fails_when=a member stays open, the dismissed
    group is listed without the flag, dismissedCount is wrong, or restore leaves a member dismissed."""
    await _vpn_world(kb.db)
    vpn = (await kb.call("GET", GAPS_PATH)).json()["groups"][0]
    resp = await kb.call("POST", f"{GAPS_PATH}/{vpn['id']}/dismiss")
    assert resp.status_code == 200 and resp.json()["status"] == "dismissed" and resp.json()["changed"] == 3
    assert {r["status"] for r in await kb.db.service_desk_gaps.find({"ticketId": {"$in": ["T1", "T2", "T3"]}}).to_list(9)} == {"dismissed"}
    assert (await _row(kb.db, "T4"))["status"] == "open"
    hidden = (await kb.call("GET", GAPS_PATH)).json()
    assert [g["count"] for g in hidden["groups"]] == [1] and hidden["dismissedCount"] == 1
    shown = (await kb.call("GET", f"{GAPS_PATH}?dismissed=true")).json()
    assert {(g["count"], g["status"]) for g in shown["groups"]} == {(3, "dismissed"), (1, "open")}
    again = await kb.call("POST", f"{GAPS_PATH}/{vpn['id']}/dismiss")
    assert again.status_code == 200 and again.json()["changed"] == 0
    back = await kb.call("POST", f"{GAPS_PATH}/{vpn['id']}/restore")
    assert back.status_code == 200 and back.json() == {"status": "open", "changed": 3}
    assert [g["count"] for g in (await kb.call("GET", GAPS_PATH)).json()["groups"]] == [3, 1]


async def test_an_unknown_or_foreign_group_answers_404_and_changes_nothing(kb):
    """protects=T-85-57 tenant scope of the group id; fails_when=another tenant's group id dismisses its rows."""
    await _gap(kb.db, "projector in room nine", "F1", tenant="t2")
    foreign = (await _row(kb.db, "F1"))["id"]
    for path in (f"{GAPS_PATH}/{foreign}/dismiss", f"{GAPS_PATH}/SDG-missing/dismiss", f"{GAPS_PATH}/SDG-missing/restore"):
        assert (await kb.call("POST", path)).status_code == 404
    assert (await _row(kb.db, "F1"))["status"] == "open"


async def test_writing_an_article_from_a_group_saves_it_for_the_desk_and_marks_the_group_written(kb):
    """protects=R6 / D-26 write-article; fails_when=the article is not a Help desk article of this tenant, a member
    is not marked written, the group is still listed, or a second press on the same group saves another article."""
    await _vpn_world(kb.db)
    vpn = (await kb.call("GET", GAPS_PATH)).json()["groups"][0]
    body = {"title": "Fix a dropping VPN", "content": "Restart the VPN app.", "tags": ["vpn"], "helpdesk": True,
            "gapGroupId": vpn["id"]}
    resp = await kb.call("POST", ARTICLES_PATH, json=body)
    assert resp.status_code == 200
    doc = await kb.db.knowledge_docs.find_one({"id": resp.json()["id"]})
    assert doc["tenantId"] == "t1" and doc["helpdesk"] is True and doc["title"] == "Fix a dropping VPN"
    assert doc["tags"] == ["vpn"] and doc["createdBy"] == "manager" and doc["updatedAt"]
    assert {r["status"] for r in await kb.db.service_desk_gaps.find({"ticketId": {"$in": ["T1", "T2", "T3"]}}).to_list(9)} == {"written"}
    assert [g["count"] for g in (await kb.call("GET", GAPS_PATH)).json()["groups"]] == [1]
    assert (await kb.call("POST", ARTICLES_PATH, json=body)).status_code == 404
    assert await kb.db.knowledge_docs.count_documents({"tenantId": "t1"}) == 1


async def test_an_article_from_a_group_must_be_a_help_desk_article_or_nothing_is_claimed(kb):
    """protects=WR-203 / D-26 / D-17 a gap leaves the list only when an article the desk can cite answers it;
    fails_when=a non-Help-desk article from a gap saves an article, marks a member written or hides the group, or
    the refusal is not the desk sentence; also fails_when=helpdesk false without a group is refused."""
    await _vpn_world(kb.db)
    vpn = (await kb.call("GET", GAPS_PATH)).json()["groups"][0]
    body = {"title": "Fix a dropping VPN", "content": "Restart the VPN app.", "tags": [], "helpdesk": False,
            "gapGroupId": vpn["id"]}
    refused = await kb.call("POST", ARTICLES_PATH, json=body)
    assert refused.status_code == 422
    assert refused.json()["detail"] == messages.API_DETAIL["gap_article_not_helpdesk"]
    assert await kb.db.knowledge_docs.count_documents({"tenantId": "t1"}) == 0
    rows = await kb.db.service_desk_gaps.find({"ticketId": {"$in": ["T1", "T2", "T3"]}}).to_list(9)
    assert len(rows) == 3 and {r["status"] for r in rows} == {"open"}
    listed = (await kb.call("GET", GAPS_PATH)).json()["groups"]
    assert [g["count"] for g in listed] == [3, 1] and listed[0]["id"] == vpn["id"]
    plain = await kb.call("POST", ARTICLES_PATH, json={"title": "Plain", "content": "Steps.", "helpdesk": False})
    assert plain.status_code == 200
    assert (await kb.db.knowledge_docs.find_one({"id": plain.json()["id"]}))["helpdesk"] is False
    assert {r["status"] for r in await kb.db.service_desk_gaps.find({"ticketId": {"$in": ["T1", "T2", "T3"]}}).to_list(9)} == {"open"}


async def test_an_article_without_a_group_is_still_saved_and_is_validated_like_an_edit(kb):
    """protects=T-85-59 the same text rules as the edit route; fails_when=an empty title or an over-long text is saved."""
    ok = await kb.call("POST", ARTICLES_PATH, json={"title": "Plain", "content": "Steps.", "tags": []})
    assert ok.status_code == 200 and (await kb.db.knowledge_docs.find_one({"id": ok.json()["id"]}))["helpdesk"] is True
    assert (await kb.call("POST", ARTICLES_PATH, json={"title": " ", "content": "Steps."})).status_code == 422
    assert (await kb.call("POST", ARTICLES_PATH, json={"title": "T", "content": "a" * OVER})).status_code == 422
    assert await kb.db.knowledge_docs.count_documents({"tenantId": "t1"}) == 1


async def test_the_gap_routes_need_ticket_access_and_article_permission_together(kb):
    """protects=D-27 / T-85-56; fails_when=a Knowledge Base editor without ticket access, a ticket user without the
    article permission, or a reader reaches any gap route, or the platform tenant is served."""
    await _gap(kb.db, "projector in room nine", "P1")
    group = (await _row(kb.db, "P1"))["id"]
    calls = [("GET", GAPS_PATH, None), ("POST", f"{GAPS_PATH}/{group}/dismiss", None),
             ("POST", f"{GAPS_PATH}/{group}/restore", None),
             ("POST", ARTICLES_PATH, {"title": "T", "content": "C", "gapGroupId": group})]
    for who in ("editor", "agent", "reader"):
        for method, path, payload in calls:
            assert (await kb.call(method, path, who=who, json=payload)).status_code == 403, (who, path)
    assert (await _row(kb.db, "P1"))["status"] == "open" and await kb.db.knowledge_docs.count_documents({}) == 0
    for method, path, payload in calls:
        resp = await kb.call(method, path, tenant="platform-admin", json=payload)
        assert resp.status_code == 403 and resp.json()["detail"] == messages.API_DETAIL["platform_tenant"]
    assert (await kb.call("GET", GAPS_PATH)).status_code == 200


async def test_the_gap_list_says_when_the_desk_is_off(kb):
    """protects=the Off notice on the gaps tab; fails_when=deskOff ignores serviceDesk.mode."""
    await kb.db.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"serviceDesk": {"mode": "off"}}}, upsert=True)
    assert (await kb.call("GET", GAPS_PATH)).json()["deskOff"] is True
