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
