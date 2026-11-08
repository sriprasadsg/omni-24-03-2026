"""The gate's side of the service desk (Phase 85, plan 85-04, DESK-01 / DESK-05).
Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py.

Value: protects=the D-03 outcome matrix (only Undoable-auto, shadow off, no stop, no force_suggest and
under 20 an hour posts), the desk's own hourly pool (the 21st answer is a draft, nobody is paged, security
actions are untouched), drafts that never expire, approve and deny closed to desk rows, a pluggable undo
that fails closed, no ticket command ever written to an agent queue, a reconciler that leaves desk rows
alone, and Activity rows that link to their ticket; fails_when=Suggest or a forced suggestion posts, the
21st answer becomes an approval card or a page, a draft expires, a draft can be approved from Activity,
a desk undo runs without a registered handler, a ticket command reaches an agent, or an Activity row loses
its ticket link or shows Undo when it cannot work; no_claim=the desk's own undo handler and breaker
(plan 85-18).
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import approvals, desk_gate, dispatch_check, gate, ledger, messages, reconciler, views
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_platform_stop, seed_tenant

DESK = {"ticketId": "k1", "ticketNumber": "TKT-0001", "title": "VPN drops", "phase": "drafted"}


@pytest.fixture
async def world(mongo_db):  # noqa: F811
    await ledger.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1", shadow=False)
    await seed_tenant(mongo_db, "t2", shadow=False)
    await mongo_db.tickets.insert_many([
        {"id": f"k{i}", "tenantId": "t1", "ticket_number": f"TKT-{i:04d}", "title": f"Ticket {i}"} for i in range(1, 30)
    ] + [{"id": "other", "tenantId": "t2", "ticket_number": "TKT-9000", "title": "Other tenant"}])
    return mongo_db


def desk_request(tenant, ticket_id, *, force_suggest=False, **extra):
    """The ActionRequest the desk pipeline sends (kind servicedesk, dispatcher service_desk, no targets)."""
    desk = {**DESK, "ticketId": ticket_id, "ticketNumber": f"TKT-{ticket_id}"}
    return gate.ActionRequest(
        tenant_id=tenant, kind="servicedesk", origin="service_desk", actions=["ticket_answer"], targets=[],
        params={"ticketId": ticket_id}, dedupe_key=f"{tenant}|service_desk|{ticket_id}",
        reason={"ruleId": "service_desk:answer", "inputs": {"suggestionOnly": True}}, dispatcher="service_desk",
        desk=desk, force_suggest=force_suggest, **extra)


async def _decide(db, req, *, master_shadow=False):
    return await gate.decide(db, req, master_shadow=master_shadow)


async def _rows(db, tenant="t1", **flt):
    return await db.autonomy_actions.find({"tenantId": tenant, **flt}, {"_id": 0}).to_list(100)


async def _set(db, tenant, **fields):
    await db.autonomy_settings.update_one({"tenantId": tenant}, {"$set": fields})


# ---------------------------------------------------------------- Task 1: the D-03 matrix

async def test_undoable_auto_with_everything_clear_posts(world):
    """protects=D-03: the one case that posts."""
    d = await _decide(world, desk_request("t1", "k1"))
    assert (d.outcome, d.state, d.shadow) == ("allow_auto", "dispatching", False)
    (row,) = await _rows(world)
    assert row["state"] == "dispatching" and row["autoDispatched"] is True


async def test_suggest_level_gives_a_draft(world):
    await _set(world, "t1", level="suggest")
    d = await _decide(world, desk_request("t1", "k1"))
    assert (d.outcome, d.state, d.reason) == ("suggest", "suggested", "level_suggest")


async def test_force_suggest_gives_a_draft_even_at_undoable_auto(world):
    """protects=PROH-85-10: a tenant at Undoable-auto whose desk switch is Drafts only never posts."""
    d = await _decide(world, desk_request("t1", "k1", force_suggest=True))
    assert (d.outcome, d.state, d.reason) == ("suggest", "suggested", "suggest_requested")
    assert await _rows(world, state="dispatching") == []
    assert await _rows(world, autoDispatched=True) == []


async def test_shadow_records_what_would_have_happened(world):
    await _set(world, "t1", shadow=True)
    d = await _decide(world, desk_request("t1", "k1"))
    assert d.state == "shadow" and d.would_have == "allow_auto" and d.shadow is True
    (row,) = await _rows(world)
    assert row["state"] == "shadow" and row["wouldHave"] == "allow_auto"


async def test_the_deployment_master_shadow_also_wins(world):
    d = await _decide(world, desk_request("t1", "k1"), master_shadow=True)
    assert d.state == "shadow" and d.would_have == "allow_auto"


async def test_a_tenant_stop_is_a_recorded_refusal(world):
    await _set(world, "t1", stop={"active": True, "by": "admin", "at": datetime.now(timezone.utc)})
    d = await _decide(world, desk_request("t1", "k1"))
    assert (d.outcome, d.reason, d.recorded) == ("refuse", "tenant_stop", True)
    (row,) = await _rows(world)
    assert row["state"] == "refused"


async def test_a_platform_stop_is_a_recorded_refusal(world):
    await seed_platform_stop(world)
    d = await _decide(world, desk_request("t1", "k1"))
    assert (d.outcome, d.reason) == ("refuse", "platform_stop")


async def test_level_off_records_nothing(world):
    await _set(world, "t1", level="off")
    d = await _decide(world, desk_request("t1", "k1"))
    assert (d.outcome, d.reason, d.recorded) == ("refuse", "level_off", False)
    assert await _rows(world) == []


async def test_an_unticked_tenant_records_nothing(world):
    await seed_tenant(world, "t3", shadow=False, ticked=False)
    d = await _decide(world, desk_request("t3", "k1"))
    assert (d.outcome, d.reason, d.recorded) == ("refuse", "not_enabled", False)
    assert await _rows(world, tenant="t3") == []


async def test_a_ticket_of_another_tenant_or_no_ticket_is_refused(world):
    d = await _decide(world, desk_request("t1", "other"))
    assert (d.outcome, d.reason) == ("refuse", "cross_tenant_target")
    d = await _decide(world, desk_request("t1", "missing"))
    assert (d.outcome, d.reason) == ("refuse", "cross_tenant_target")
    assert await _rows(world, state={"$in": ["dispatching", "suggested", "executed"]}) == []


async def test_an_agent_target_on_a_desk_request_is_refused(world):
    req = desk_request("t1", "k1")
    req.targets = ["agent-1"]
    d = await _decide(world, req)
    assert (d.outcome, d.reason) == ("refuse", "invalid_target")


# ---------------------------------------------------------------- Task 1: the desk's own hourly pool

async def _seed_rows(db, n, *, kind, tenant="t1", minutes=10, tag="s"):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    docs = []
    for i in range(n):
        created = now - timedelta(minutes=minutes, seconds=i)
        docs.append({"id": f"AO-{tag}-{kind}-{i}", "tenantId": tenant, "kind": kind, "state": "executed",
                     "autoDispatched": True, "createdAt": created, "updatedAt": created, "finishedAt": created,
                     "command": "ticket_answer" if kind == ledger.DESK_KIND else "block_ip", "targets": [],
                     "reason": {"ruleId": "t", "inputs": {}}})
    if docs:
        await db.autonomy_actions.insert_many(docs)


async def test_the_limit_is_twenty_and_is_the_desk_constant():
    from service_desk import DESK_RATE_LIMIT
    assert desk_gate.DESK_RATE_LIMIT == DESK_RATE_LIMIT == 20


async def test_the_21st_answer_in_an_hour_is_a_draft_and_nobody_is_told(world):
    """protects=D-30 / D-22 / PROH-85-07: a draft with the desk's own code, never an approval card, no
    notification and no on-call document."""
    await _seed_rows(world, 20, kind=ledger.DESK_KIND)
    d = await _decide(world, desk_request("t1", "k21"))
    assert (d.outcome, d.state, d.reason) == ("suggest", "suggested", "desk_rate_limit")
    (row,) = await _rows(world, state="suggested")
    assert row["reasonCode"] == "desk_rate_limit" and row["reasonText"] == messages.REASON_TEXT["desk_rate_limit"]
    assert row["approval"]["requiredBy"] == "desk_rate_limit"
    assert await _rows(world, state="awaiting_approval") == []
    assert await world.notifications.count_documents({}) == 0
    for name in await world.list_collection_names():
        if "oncall" in name.lower() or "on_call" in name.lower():
            assert await world[name].count_documents({}) == 0, name
    marker = await world.autonomy_settings.find_one({"tenantId": "t1"})
    assert marker.get("rateLimitNotifiedAt") is None


async def test_nineteen_answers_still_post(world):
    await _seed_rows(world, 19, kind=ledger.DESK_KIND)
    d = await _decide(world, desk_request("t1", "k20"))
    assert (d.outcome, d.state) == ("allow_auto", "dispatching")


async def test_rows_older_than_an_hour_do_not_count(world):
    await _seed_rows(world, 20, kind=ledger.DESK_KIND, minutes=90)
    d = await _decide(world, desk_request("t1", "k21"))
    assert d.state == "dispatching"


async def test_twenty_desk_rows_leave_the_security_limit_untouched(world):
    """protects=D-30: a ticket flood never pushes a security action to approval."""
    await _seed_rows(world, 20, kind=ledger.DESK_KIND)
    await world.agents.insert_one({"id": "a1", "tenantId": "t1", "hostname": "h1", "ipAddress": "10.1.1.5"})
    req = gate.ActionRequest(tenant_id="t1", kind="security", origin="test", actions=["block_ip"], targets=["a1"],
                             params={"ip_address": "203.0.113.7"}, dedupe_key="t1|block_ip|203.0.113.7")
    d = await _decide(world, req)
    assert (d.outcome, d.state) == ("allow_auto", "dispatching")


async def test_twenty_security_rows_do_not_limit_the_desk(world):
    await _seed_rows(world, 20, kind="security")
    d = await _decide(world, desk_request("t1", "k21"))
    assert d.state == "dispatching"


async def test_an_unreadable_pool_count_drafts_instead(world, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr(ledger, "count_auto_since", boom)
    d = await _decide(world, desk_request("t1", "k1"))
    assert (d.outcome, d.reason) == ("suggest", "desk_rate_limit")


# ---------------------------------------------------------------- Task 1: drafts never expire

async def test_a_draft_has_no_expiry_and_expire_due_leaves_it(world):
    """protects=research default: a draft waits on the ticket until a person sends, edits or discards it."""
    await _decide(world, desk_request("t1", "k1", force_suggest=True))
    (row,) = await _rows(world)
    assert row["state"] == "suggested" and row["approval"]["expiresAt"] is None
    assert await approvals.expire_due(world, now=datetime.now(timezone.utc) + timedelta(hours=25)) == 0
    (row,) = await _rows(world)
    assert row["state"] == "suggested"


async def test_another_dispatchers_suggestion_still_expires(world):
    """No behaviour change for every other row: a card keeps its 24 hour expiry."""
    await world.agents.insert_one({"id": "a1", "tenantId": "t1", "hostname": "h1", "ipAddress": "10.1.1.5"})
    req = gate.ActionRequest(tenant_id="t1", kind="security", origin="test", actions=["block_ip"], targets=["a1"],
                             params={"ip_address": "203.0.113.7"}, dedupe_key="t1|block_ip|203.0.113.7",
                             force_suggest=True)
    await _decide(world, req)
    (row,) = await _rows(world)
    assert isinstance(row["approval"]["expiresAt"], datetime)
