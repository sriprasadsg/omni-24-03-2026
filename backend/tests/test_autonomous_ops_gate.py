"""Autonomous Ops gate (Phase 81, plan 81-01): the one decision function, the write-ahead
decision ledger and the audit mirror. Real MongoDB (skips without one) through the
throwaway database of tests/_mongo_test_db.py; nothing touches the live database.

Value: protects=an eligible tenant's request is decided once, recorded in autonomy_actions
BEFORE anything is dispatched, mirrored into the hash-chained audit ledger and listed under
the right bucket; a tenant without the Autonomous Ops screen tick is Off and leaves no row,
no audit event; a ledger that cannot be written refuses the decision and dispatches nothing;
fails_when=a decision is returned without a row, an unticked tenant leaves a trace, an
instruction is written in shadow mode or without a ledger row, or the audit chain breaks;
no_claim=the remaining GATE-03 steps (stop, level, never-touch, caps, dedupe), which plan
81-11 adds and enumerates.
"""
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import audit_ledger
from autonomous_ops import gate, ledger
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_agent, seed_tenant

IP = "203.0.113.7"


def _block_ip(tenant_id, agent_id="a1", ip=IP):
    return gate.ActionRequest(tenant_id=tenant_id, kind="security", origin="test", actions=["block_ip"],
                              targets=[agent_id], params={"ip_address": ip},
                              dedupe_key=f"{tenant_id}|block_ip|{ip}",
                              reason={"ruleId": "playbook:block_ip", "inputs": {"ip": ip}})


@pytest.fixture(autouse=True)
def _default_master(monkeypatch):
    monkeypatch.delenv("AUTONOMOUS_REMEDIATION_DRY_RUN", raising=False)  # unset = shadow on


async def test_tracer_shadow_decision_is_written_ahead_and_listed(mongo_db):
    """Tracer. protects=GATE-03 / GATE-07 / GATE-09: the decision exists as one shadow row,
    nothing is dispatched, the audit chain holds the matching event and the list shows it."""
    await ledger.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1")
    await seed_agent(mongo_db, "t1", "a1", hostname="h1", ip="10.1.1.5")

    decision = await gate.decide(mongo_db, _block_ip("t1"))

    assert (decision.outcome, decision.state, decision.would_have) == ("allow_auto", "shadow", "allow_auto")
    assert decision.recorded is True and decision.shadow is True and decision.action_id
    rows = await mongo_db.autonomy_actions.find({"tenantId": "t1"}).to_list(10)
    assert [r["id"] for r in rows] == [decision.action_id]
    assert rows[0]["state"] == "shadow" and rows[0]["wouldHave"] == "allow_auto"
    stored = await ledger.get(mongo_db, "t1", decision.action_id)
    assert stored["createdAt"].tzinfo is not None
    assert await mongo_db.agent_instructions.count_documents({}) == 0
    assert await mongo_db.response_tasks.count_documents({}) == 0

    report = await audit_ledger.verify("t1", db=mongo_db)
    assert report["valid"] and report["total_records"] >= 1
    event = await mongo_db.audit_logs.find_one({"tenantId": "t1", "action": "autonomous_ops.shadow"})
    assert event and event["resourceId"] == decision.action_id

    sim = await ledger.list_actions(mongo_db, "t1", bucket="simulation")
    assert [i["id"] for i in sim["items"]][:1] == [decision.action_id]
    done = await ledger.list_actions(mongo_db, "t1", bucket="done")
    assert done["items"] == [] and done["nextCursor"] is None


async def test_unticked_tenant_is_off_and_unrecorded(mongo_db):
    """protects=D-23 / GATE-02: no tick = Off; refused not_enabled, and no row, no audit event."""
    await ledger.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t2", ticked=False)

    decision = await gate.decide(mongo_db, _block_ip("t2"))

    assert (decision.outcome, decision.reason, decision.recorded) == ("refuse", "not_enabled", False)
    assert decision.action_id is None
    assert await mongo_db.autonomy_actions.count_documents({"tenantId": "t2"}) == 0
    assert await mongo_db.audit_logs.count_documents({"tenantId": "t2"}) == 0


async def test_platform_tenant_is_always_off(mongo_db):
    """protects=D-04: platform-admin is Off whatever it is ticked or stored as."""
    await ledger.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "platform-admin")

    decision = await gate.decide(mongo_db, _block_ip("platform-admin"))

    assert (decision.outcome, decision.reason, decision.recorded) == ("refuse", "platform_tenant", False)
    assert await mongo_db.autonomy_actions.count_documents({}) == 0
    assert await mongo_db.audit_logs.count_documents({}) == 0


async def test_class_step_escalates_approve_actions_and_refuses_unregistered(mongo_db):
    """protects=GATE-04: an approve action never decides allow_auto (it needs approval), and a
    name outside the registry, an undo-only name or a probe is refused unregistered_action."""
    await ledger.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1", shadow=False)
    mongo_db_shadow_off = {"master_shadow": False}

    iso = gate.ActionRequest(tenant_id="t1", kind="security", origin="test", actions=["isolate_host"],
                             targets=["a1"], params={}, dedupe_key="t1|isolate|a1")
    d = await gate.decide(mongo_db, iso, **mongo_db_shadow_off)
    assert (d.outcome, d.state, d.reason) == ("needs_approval", "awaiting_approval", "class_approve")
    row = await ledger.get(mongo_db, "t1", d.action_id)
    assert row["approval"]["expiresAt"] - row["createdAt"] == gate.APPROVAL_TTL

    raised = gate.ActionRequest(tenant_id="t1", kind="security", origin="test", actions=["block_ip"],
                                targets=["a1"], params={"ip_address": IP}, dedupe_key="t1|raised",
                                playbook_raise=True)
    d = await gate.decide(mongo_db, raised, **mongo_db_shadow_off)
    assert (d.outcome, d.reason) == ("needs_approval", "playbook_raised")

    for name in ("rm_rf", "unblock_ip", "scan_file"):
        bad = gate.ActionRequest(tenant_id="t1", kind="security", origin="test", actions=[name],
                                 targets=["a1"], params={}, dedupe_key=f"t1|{name}")
        d = await gate.decide(mongo_db, bad, **mongo_db_shadow_off)
        assert (d.outcome, d.reason) == ("refuse", "unregistered_action"), name

    auto = await gate.decide(mongo_db, _block_ip("t1"), **mongo_db_shadow_off)
    assert (auto.outcome, auto.state) == ("allow_auto", "dispatching")
    row = await ledger.get(mongo_db, "t1", auto.action_id)
    assert row["autoDispatched"] is True and row["state"] == "dispatching"

    sug = await gate.suggest(mongo_db, _block_ip("t1", ip="203.0.113.9"), **mongo_db_shadow_off)
    assert (sug.outcome, sug.state) == ("suggest", "suggested")


async def test_a_ledger_that_cannot_be_written_refuses_the_decision(mongo_db):
    """protects=GATE-07: when the insert raises, decide refuses ledger_unavailable and no
    instruction or response task is written."""
    await seed_tenant(mongo_db, "t1", shadow=False)

    class _Broken:
        async def insert_one(self, *_a, **_k):
            raise RuntimeError("disk full")

    with patch.object(ledger, "_actions", lambda _db: _Broken()):
        decision = await gate.decide(mongo_db, _block_ip("t1"), master_shadow=False)

    assert (decision.outcome, decision.reason, decision.recorded) == ("refuse", "ledger_unavailable", False)
    assert await mongo_db.agent_instructions.count_documents({}) == 0
    assert await mongo_db.response_tasks.count_documents({}) == 0
