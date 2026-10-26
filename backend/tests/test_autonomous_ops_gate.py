"""Autonomous Ops gate (Phase 81, plan 81-01): the one decision function, the write-ahead
decision ledger and the audit mirror. Real MongoDB (skips without one) through the
throwaway database of tests/_mongo_test_db.py; nothing touches the live database.

Value: protects=an eligible tenant's request is decided once, recorded in autonomy_actions
BEFORE anything is dispatched, mirrored into the hash-chained audit ledger and listed under
the right bucket; a tenant without the Autonomous Ops screen tick is Off and leaves no row,
no audit event; a ledger that cannot be written refuses the decision and dispatches nothing;
fails_when=a decision is returned without a row, an unticked tenant leaves a trace, an
instruction is written in shadow mode or without a ledger row, or the audit chain breaks;
no_claim=the remaining GATE-03 steps (stop, level, never-touch, caps, dedupe), which
test_autonomous_ops_gate_order.py (plan 81-11) enumerates.
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
    await seed_agent(mongo_db, "t1", "a1", ip="198.51.100.11")
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
    await seed_agent(mongo_db, "t1", "a1", ip="198.51.100.11")

    class _Broken:
        async def insert_one(self, *_a, **_k):
            raise RuntimeError("disk full")

    with patch.object(ledger, "_actions", lambda _db: _Broken()):
        decision = await gate.decide(mongo_db, _block_ip("t1"), master_shadow=False)

    assert (decision.outcome, decision.reason, decision.recorded) == ("refuse", "ledger_unavailable", False)
    assert await mongo_db.agent_instructions.count_documents({}) == 0
    assert await mongo_db.response_tasks.count_documents({}) == 0


# ---------------------------------------------------------------- plan 81-11, Task 1 (tracer)

def _own_address() -> str:
    """An address of one of this host's own interfaces, as the never-touch list sees it."""
    import socket

    import psutil
    for addrs in psutil.net_if_addrs().values():
        for item in addrs:
            if item.family == socket.AF_INET and not item.address.startswith("127."):
                return item.address
    return "127.0.0.1"


async def test_tracer_own_address_is_refused_protected_target_at_every_level(mongo_db):
    """Tracer. protects=GATE-08 / PROH-81-03: a block_ip aimed at the backend's own address is
    refused protected_target through gate.decide, recorded with the plain-words reason, even at
    Suggest, and writes no instruction."""
    from autonomous_ops import messages
    await ledger.ensure_indexes(mongo_db)
    own = _own_address()
    for tenant, level in (("t1", "undoable_auto"), ("t2", "suggest")):
        await seed_tenant(mongo_db, tenant, level=level, shadow=False)
        await seed_agent(mongo_db, tenant, f"{tenant}-a1", ip="198.51.100.11" if tenant == "t1" else "198.51.100.12")
        d = await gate.decide(mongo_db, _block_ip(tenant, agent_id=f"{tenant}-a1", ip=own), master_shadow=False)
        assert (d.outcome, d.state, d.reason, d.recorded) == ("refuse", "refused", "protected_target", True), tenant
        rows = await mongo_db.autonomy_actions.find({"tenantId": tenant}).to_list(5)
        assert len(rows) == 1 and rows[0]["state"] == "refused" and rows[0]["reasonCode"] == "protected_target"
        assert rows[0]["reasonText"] == messages.REASON_TEXT["protected_target"]
    assert await mongo_db.agent_instructions.count_documents({}) == 0
    assert await mongo_db.response_tasks.count_documents({}) == 0


async def test_platform_agent_address_other_tenant_target_and_empty_targets_are_refused(mongo_db):
    """protects=GATE-08 / D-17: a block_ip for the address of a platform-admin agent is
    protected_target; a target agent of another tenant (or none) is cross_tenant_target; an
    empty target list is no_target."""
    await ledger.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1", shadow=False)
    await seed_agent(mongo_db, "t1", "a1", ip="198.51.100.11")
    await seed_agent(mongo_db, "t9", "b1", ip="198.51.100.19")
    await seed_agent(mongo_db, "platform-admin", "pa1", ip="198.51.100.77")
    kw = {"master_shadow": False}

    d = await gate.decide(mongo_db, _block_ip("t1", ip="198.51.100.77"), **kw)
    assert (d.outcome, d.reason) == ("refuse", "protected_target")
    for target in ("b1", "pa1", "ghost"):
        d = await gate.decide(mongo_db, _block_ip("t1", agent_id=target), **kw)
        assert (d.outcome, d.reason) == ("refuse", "cross_tenant_target"), target
    empty = _block_ip("t1")
    empty.targets = []
    d = await gate.decide(mongo_db, empty, **kw)
    assert (d.outcome, d.reason) == ("refuse", "no_target")
    assert await mongo_db.agent_instructions.count_documents({}) == 0


def test_messages_cover_every_reason_code_and_every_registry_command():
    """protects=ACTV-01 / ACTV-08: every code decide can record has plain words, every command
    has a label, and no user-visible text uses a banned term."""
    import re

    from autonomous_ops import messages, registry
    assert set(messages.REASON_TEXT) >= set(gate.REASON_CODES)
    assert set(messages.ACTION_LABELS) >= set(registry.commands())
    assert messages.PLATFORM_ADMIN_DISPLAY == "Platform administrator"
    assert messages.simulation_result("block 203.0.113.7") == \
        "Nothing was done. This is what would have happened: block 203.0.113.7."
    texts = [*messages.ACTION_LABELS.values(), *messages.CLASS_LINES.values(), *messages.CONTROL_LABELS.values(),
             *messages.REASON_TEXT.values(), *[t for pair in messages.NOTICES.values() for t in pair]]
    banned = re.compile(r"\b(ASI|AGI)\b|autopilot|fully[ -]autonomous|roll(ed|ing)?[ -]?back", re.IGNORECASE)
    assert [t for t in texts if banned.search(t)] == []
