"""Service desk rows in the Autonomous Ops ledger (Phase 85, plan 85-03, DESK-01 / DESK-02).
Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py.

Value: protects=the gate takes a ticket action from the service desk only and only on a ticket of the
caller's own tenant, desk rows are counted in their own automatic-action pool and never reach the
Phase 81 breaker, every hand-off is an audited ledger row and the draft lifecycle can be recorded
without a state change; fails_when=another dispatcher can post a ticket answer, a cross-tenant ticket
is accepted, 20 desk rows push security actions to approval, three withdrawn answers lower the tenant's
level, or a hand-off or desk update leaves no audit event; no_claim=the desk pipeline that calls these
(plans 85-01 and later).
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import audit_ledger
from autonomous_ops import breaker, gate, ledger, messages, registry, settings, views
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_tenant

DESK = {"ticketId": "k1", "ticketNumber": "TKT-0001", "title": "VPN drops", "phase": "drafted"}


@pytest.fixture
async def world(mongo_db):  # noqa: F811
    await ledger.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1", shadow=False)
    await seed_tenant(mongo_db, "t2", shadow=False)
    await mongo_db.tickets.insert_many([
        {"id": "k1", "tenantId": "t1", "ticket_number": "TKT-0001", "title": "VPN drops"},
        {"id": "k3", "tenantId": "t1", "ticket_number": "TKT-0003", "title": "Printer"},
        {"id": "k2", "tenantId": "t2", "ticket_number": "TKT-0002", "title": "Other tenant"}])
    return mongo_db


def _desk_req(ticket="k1", *, tenant="t1", actions=("ticket_answer",), targets=(), dispatcher="service_desk",
              desk=DESK, params=None, **extra):
    return gate.ActionRequest(
        tenant_id=tenant, kind="servicedesk", origin="service_desk", actions=list(actions), targets=list(targets),
        params={"ticketId": ticket} if params is None else params, dedupe_key=f"{tenant}|service_desk|{ticket}",
        reason={"ruleId": "service_desk:answer", "inputs": {"suggestionOnly": True}}, dispatcher=dispatcher,
        desk=dict(desk) if desk is not None else None, **extra)


async def _decide(db, req):
    return await gate.decide(db, req, master_shadow=False)


async def _rows(db, tenant="t1", **flt):
    return await db.autonomy_actions.find({"tenantId": tenant, **flt}, {"_id": 0}).to_list(50)


# ---------------------------------------------------------------- Task 1: the gate seam

async def test_a_desk_answer_on_the_callers_own_ticket_is_allowed_and_keeps_its_desk_subdocument(world):
    """protects=DESK-01: allowed automatically with no agent target; the row says service_desk / servicedesk
    and carries the request's desk dict unchanged."""
    d = await _decide(world, _desk_req("k1"))
    assert (d.outcome, d.state, d.reason) == ("allow_auto", "dispatching", "class_auto")
    (row,) = await _rows(world)
    assert row["dispatcher"] == "service_desk" and row["kind"] == "servicedesk" and row["targets"] == []
    assert row["desk"] == DESK
    assert row["command"] == "ticket_answer" and row["undo"]["action"] == "ticket_withdraw"
    assert row["autoDispatched"] is True
    assert await world.agent_instructions.count_documents({}) == 0       # never sent to an agent


async def test_force_suggest_records_a_suggestion_with_the_desk_subdocument(world):
    d = await _decide(world, _desk_req("k3", force_suggest=True, desk={**DESK, "ticketId": "k3"}))
    assert (d.outcome, d.state) == ("suggest", "suggested")
    (row,) = await _rows(world)
    assert row["state"] == "suggested" and row["desk"]["ticketId"] == "k3"


async def test_any_other_dispatcher_is_refused_and_leaves_no_row(world):
    """protects=T-85-02: ticket_answer is unregistered for every dispatcher but the service desk."""
    d = await _decide(world, _desk_req("k1", dispatcher="instruction"))
    assert (d.outcome, d.reason, d.recorded) == ("refuse", "unregistered_action", False)
    assert await _rows(world) == []


@pytest.mark.parametrize("kw,code", [({"targets": ["agent-1"]}, "invalid_target"),
                                     ({"params": {}}, "no_target"),
                                     ({"params": {"ticketId": ""}}, "no_target"),
                                     ({"params": {"ticketId": 7}}, "no_target"),
                                     ({"ticket": "k2"}, "cross_tenant_target"),
                                     ({"ticket": "missing"}, "cross_tenant_target")])
async def test_a_bad_ticket_target_is_refused_and_nothing_is_dispatched(world, kw, code):
    """protects=T-85-02: an agent target, no ticket and another tenant's ticket are all refused; none
    leaves a dispatching, suggested or executed row."""
    ticket = kw.pop("ticket", "k1")
    d = await _decide(world, _desk_req(ticket, **kw))
    assert (d.outcome, d.reason) == ("refuse", code)
    assert await _rows(world, state={"$in": ["dispatching", "suggested", "executed"]}) == []


async def test_an_unreadable_ticket_collection_refuses_closed(world):
    from unittest.mock import patch
    with patch("autonomous_ops.desk_gate.raw", side_effect=RuntimeError("down")):
        d = await _decide(world, _desk_req("k1"))
    assert (d.outcome, d.reason) == ("refuse", "protected_target")


async def test_a_request_without_desk_stores_no_desk_key(world):
    await world.agents.insert_one({"id": "a1", "tenantId": "t1", "hostname": "h1", "ipAddress": "10.1.1.5"})
    req = gate.ActionRequest(tenant_id="t1", kind="security", origin="test", actions=["block_ip"], targets=["a1"],
                             params={"ip_address": "203.0.113.7"}, dedupe_key="t1|block_ip|203.0.113.7")
    d = await _decide(world, req)
    assert d.recorded
    (row,) = await _rows(world)
    assert "desk" not in row


def test_the_desk_words_are_declared_once_in_the_autonomous_ops_messages():
    assert messages.ACTION_LABELS["ticket_answer"] == "Post ticket answer"
    assert messages.ACTION_LABELS["ticket_withdraw"] == "Withdraw ticket answer"
    assert messages.ACTION_LABELS["ticket_handoff"] == "Send ticket to a person"
    assert messages.DESK_ACTION_LABELS == {"draft": "Draft ticket answer"}
    assert messages.DESK_UNDO_HINT == "Hides the answer from the requester and sends the ticket to a person."
    assert messages.REASON_TEXT["desk_rate_limit"] == "20 answers were posted in the last hour, so this one is a draft."
    assert messages.API_DETAIL["desk_draft"] == "Send, edit or discard this draft on the ticket."


# ---------------------------------------------------------------- Task 2: two pools, desk rows outside the breaker

async def _seed(db, n, *, kind, state="executed", auto=True, minutes=10, tenant="t1", finished=None, tag="s"):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    docs = []
    for i in range(n):
        created = now - timedelta(minutes=minutes, seconds=i)
        docs.append({"id": f"AO-{tag}-{kind}-{state}-{i}", "tenantId": tenant, "kind": kind, "state": state,
                     "autoDispatched": auto, "createdAt": created, "updatedAt": created,
                     "finishedAt": finished if finished is not None else created, "command": "ticket_answer"
                     if kind == ledger.DESK_KIND else "block_ip", "targets": [],
                     "reason": {"ruleId": "t", "inputs": {}}})
    if docs:
        await db.autonomy_actions.insert_many(docs)


async def test_twenty_desk_rows_leave_the_actions_pool_empty(world):
    """protects=D-30 / PROH-85-08 / T-85-09: a ticket flood is counted only in the desk pool."""
    await _seed(world, 20, kind=ledger.DESK_KIND)
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    assert await ledger.count_auto_since(world, "t1", since) == 0
    assert await ledger.count_auto_since(world, "t1", since, pool="actions") == 0
    assert await ledger.count_auto_since(world, "t1", since, pool="servicedesk") == 20


async def test_twenty_security_rows_leave_the_desk_pool_empty(world):
    await _seed(world, 20, kind="security")
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    assert await ledger.count_auto_since(world, "t1", since) == 20
    assert await ledger.count_auto_since(world, "t1", since, pool="servicedesk") == 0


async def test_shadow_and_control_rows_are_in_neither_pool(world):
    await _seed(world, 1, kind=ledger.DESK_KIND, state="shadow", tag="a")
    await _seed(world, 1, kind="control", state="recorded", tag="b")
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    assert await ledger.count_auto_since(world, "t1", since) == 0
    assert await ledger.count_auto_since(world, "t1", since, pool="servicedesk") == 0


async def test_a_flood_of_desk_rows_does_not_push_a_security_action_to_approval(world):
    """protects=T-85-09 through the real gate: 20 desk rows, then an automatic block_ip is still allowed."""
    await _seed(world, 20, kind=ledger.DESK_KIND)
    await world.agents.insert_one({"id": "a1", "tenantId": "t1", "hostname": "h1", "ipAddress": "10.1.1.5"})
    req = gate.ActionRequest(tenant_id="t1", kind="security", origin="test", actions=["block_ip"], targets=["a1"],
                             params={"ip_address": "203.0.113.7"}, dedupe_key="t1|block_ip|203.0.113.7")
    d = await _decide(world, req)
    assert (d.outcome, d.reason) == ("allow_auto", "class_auto")


async def test_an_unknown_pool_is_an_error(world):
    with pytest.raises(ValueError):
        await ledger.count_auto_since(world, "t1", datetime.now(timezone.utc), pool="other")


async def test_three_withdrawn_desk_answers_never_trip_the_breaker(world):
    """protects=D-25 / PROH-85-08 / T-85-10: undone desk rows are not in recent_finished_auto."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    await _seed(world, 3, kind=ledger.DESK_KIND, state="undone", finished=now - timedelta(minutes=5))
    assert await ledger.recent_finished_auto(world, "t1", n=10) == []
    assert not await breaker.evaluate(world, "t1")
    assert (await settings.load(world, "t1")).level == "undoable_auto"


async def test_the_same_three_undone_rows_of_another_kind_still_trip_it(world):
    """The exclusion is the desk's alone: three undone security rows lower the level as before."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    await _seed(world, 3, kind="security", state="undone", finished=now - timedelta(minutes=5))
    assert await breaker.evaluate(world, "t1")


# ---------------------------------------------------------------- Task 3: hand-off rows and the desk-field updater

TICKET = {"id": "k1", "ticket_number": "TKT-0001", "title": "VPN drops"}
RESULT = "Ticket TKT-0001 went to the normal queue. The requester was told a person will look at it."
ANN = {"id": "u1", "name": "Ann"}


async def _audit(db, suffix):
    return await db.audit_logs.find({"tenantId": "t1", "action": f"autonomous_ops.servicedesk.{suffix}"}).to_list(10)


async def test_a_hand_off_is_a_finished_audited_row_the_activity_view_can_present(world):
    """protects=D-24: every hand-off is a ledger row with the full field set, one audit event, and a view
    that reads it as done with the hand-off label."""
    row = await ledger.record_desk_event(world, "t1", ticket=TICKET, reason_code="no_article",
                                         reason_text="No article matched.", activity_result=RESULT)
    assert row["id"].startswith("AO-")
    assert (row["kind"], row["dispatcher"], row["origin"]) == ("servicedesk", "service_desk", "service_desk")
    assert (row["command"], row["action"], row["actions"]) == ("ticket_handoff", "ticket_handoff", ["ticket_handoff"])
    assert (row["targets"], row["target"], row["params"]) == ([], "TKT-0001", {"ticketId": "k1"})
    assert (row["steps"], row["rollback"], row["state"], row["autoDispatched"]) == ([], [], "executed", False)
    assert row["approval"] == {"requiredBy": None, "expiresAt": None, "approver": None, "decidedAt": None}
    assert row["undo"] == {"available": False, "action": None, "params": {}, "undoneAt": None, "undoneBy": None}
    assert (row["reasonCode"], row["reasonText"], row["activityResult"]) == ("no_article", "No article matched.", RESULT)
    assert row["desk"] == {"ticketId": "k1", "ticketNumber": "TKT-0001", "title": "VPN drops",
                           "phase": "handed_off", "reason": "no_article"}
    assert row["finishedAt"] is not None
    stored = await ledger.get(world, "t1", row["id"])
    assert stored["state"] == "executed" and stored["desk"]["phase"] == "handed_off"
    assert len(await _audit(world, "handoff")) == 1
    assert (await audit_ledger.verify("t1", db=world))["valid"] is True
    shown = views.present_row(stored, viewer_is_platform_staff=False)
    assert shown["bucket"] == "done" and shown["actionLabel"] == "Send ticket to a person"
    assert shown["canUndo"] is False


async def test_a_hand_off_is_not_counted_as_an_automatic_action_or_by_the_breaker(world):
    await ledger.record_desk_event(world, "t1", ticket=TICKET, reason_code="no_article", reason_text="x",
                                   activity_result=RESULT)
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    assert await ledger.count_auto_since(world, "t1", since) == 0
    assert await ledger.count_auto_since(world, "t1", since, pool="servicedesk") == 0
    assert await ledger.recent_finished_auto(world, "t1") == []


async def test_a_failed_hand_off_insert_raises_ledger_unavailable():
    class _Down:
        class autonomy_actions:
            @staticmethod
            async def insert_one(doc):
                raise RuntimeError("down")

    with pytest.raises(ledger.LedgerUnavailable):
        await ledger.record_desk_event(_Down, "t1", ticket=TICKET, reason_code="no_article", reason_text="x",
                                       activity_result=RESULT)


async def test_set_desk_fields_changes_only_allow_listed_desk_keys_and_never_the_state(world):
    """protects=T-85-11: one update, one audit event naming the actor; an unknown key is dropped."""
    row = await ledger.record_desk_event(world, "t1", ticket=TICKET, reason_code="no_article", reason_text="x",
                                         activity_result=RESULT)
    updated = await ledger.set_desk_fields(world, "t1", row["id"],
                                           {"phase": "sent", "sentBy": ANN, "bogus": 1, "state": "failed"},
                                           event="sent", actor=ANN)
    assert updated["state"] == "executed"
    assert updated["desk"]["phase"] == "sent" and updated["desk"]["sentBy"] == ANN
    assert "bogus" not in updated["desk"] and "bogus" not in updated and updated["desk"]["ticketId"] == "k1"
    events = await _audit(world, "sent")
    assert len(events) == 1 and events[0]["actor"]["userId"] == "Ann"
    assert len(await _audit(world, "handoff")) == 1


async def test_set_desk_fields_with_nothing_allowed_or_the_wrong_tenant_changes_nothing(world):
    row = await ledger.record_desk_event(world, "t1", ticket=TICKET, reason_code="no_article", reason_text="x",
                                         activity_result=RESULT)
    assert await ledger.set_desk_fields(world, "t1", row["id"], {"bogus": 1, "state": "failed"}, event="x") is None
    assert await ledger.set_desk_fields(world, "t2", row["id"], {"phase": "sent"}, event="sent", actor=ANN) is None
    assert await ledger.set_desk_fields(world, "t1", "AO-missing", {"phase": "sent"}, event="sent") is None
    assert (await ledger.get(world, "t1", row["id"]))["desk"]["phase"] == "handed_off"
    assert await world.audit_logs.count_documents({"action": {"$regex": "servicedesk\\.(x|sent)$"}}) == 0
