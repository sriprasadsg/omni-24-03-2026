"""Autonomous Ops decision ledger and the only stamped writers (Phase 81, plan 81-01, GATE-07).
Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py.

Value: protects=no instruction or response task is written without a ledger row in a
dispatchable state; every state change appears once in the hash-chained audit log and a double
transition has exactly one winner; a stop holds back action and probe instructions but never an
undo or compensate; decision records sit outside every retention path and listing is stable
across pages; fails_when=an instruction is written for a shadow, refused, denied or expired row,
two concurrent transitions both win, the intent event follows the dispatch, a stop is bypassed,
or a retention module starts naming a decision collection; no_claim=the agent poll hold-back
(plan 81-08) and the approve/deny/undo routes (plans 81-04/81-09).
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import audit_ledger
from autonomous_ops import (DECISION_RETENTION_FLOOR_DAYS, PROTECTED_COLLECTIONS, STAMP_SOURCE, gate, ledger,
                            settings)
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import (FakeLedger, permissive_gate, seed_agent, seed_platform_stop, seed_tenant)

IP = "203.0.113.7"
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _req(tenant="t1", ip=IP, key=None, actions=("block_ip",), rollback=None):
    return gate.ActionRequest(tenant_id=tenant, kind="security", origin="test", actions=list(actions),
                              targets=["a1"], params={"ip_address": ip}, dedupe_key=key or f"{tenant}|{ip}",
                              reason={"ruleId": "playbook:block_ip", "inputs": {}}, rollback=rollback)


def _row(tenant, state, dedupe_key=None, **kw):
    now = datetime.now(timezone.utc)
    return {"tenantId": tenant, "kind": "security", "origin": "test", "state": state, "createdAt": now,
            "updatedAt": now, "reason": {"ruleId": "t", "inputs": {}}, "dedupeKey": dedupe_key, **kw}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv("AUTONOMOUS_REMEDIATION_DRY_RUN", raising=False)


@pytest.fixture
async def live(mongo_db):
    await ledger.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1", shadow=False)
    await seed_agent(mongo_db, "t1", "a1")
    return mongo_db


async def _dispatching(db, tenant="t1", ip=IP):
    undo = [{"action": "unblock_ip", "params": {"ip_address": ip}}]    # a decided compensation (81-15)
    d = await gate.decide(db, _req(tenant, ip, rollback=undo), master_shadow=False)
    assert d.state == "dispatching", d
    return d.action_id


async def _events(db, tenant="t1"):
    return await db.audit_logs.find({"tenantId": tenant}).sort("seq", 1).to_list(100)


async def test_concurrent_transitions_have_one_winner_and_one_audit_event(live):
    """Edge GATE-07 adjacency."""
    d = await gate.suggest(live, _req(), master_shadow=False)
    assert d.state == "suggested"
    results = await asyncio.gather(*(
        ledger.transition(live, "t1", d.action_id, ("awaiting_approval", "suggested"), "approved",
                          actor={"username": "alice", "tier": "tenant"}) for _ in range(2)))
    assert sorted(r is None for r in results) == [False, True]
    approved = [e for e in await _events(live) if e["action"] == "autonomous_ops.approved"]
    assert len(approved) == 1 and approved[0]["resourceId"] == d.action_id
    assert approved[0]["actor"]["userId"] == "alice"
    assert (await ledger.get(live, "t1", d.action_id))["state"] == "approved"
    # another tenant cannot move the row
    assert await ledger.transition(live, "t2", d.action_id, ("approved",), "dispatching") is None


async def test_intent_event_precedes_the_dispatch_and_the_chain_verifies(live):
    """Edge GATE-07 ordering."""
    action_id = await _dispatching(live)
    events = await _events(live)
    assert [e["action"] for e in events] == ["autonomous_ops.dispatching"]
    assert await live.agent_instructions.count_documents({}) == 0
    result = await gate.execute(live, "t1", action_id, command="block_ip", agent_id="a1", params={"ip_address": IP})
    assert result["status"] == "queued"
    instr = await live.agent_instructions.find_one({"id": result["task_id"]})
    assert events[0]["timestamp"] <= instr["created_at"]
    assert (await audit_ledger.verify("t1", db=live))["valid"]


async def test_execute_writes_one_stamped_instruction_and_links_it(live):
    action_id = await _dispatching(live)
    result = await gate.execute(live, "t1", action_id, command="block_ip", agent_id="a1", params={"ip_address": IP})
    doc = await live.agent_instructions.find_one({"id": result["task_id"]}, {"_id": 0})
    assert doc["type"] == "block_ip" and doc["agent_id"] == "a1" and doc["tenantId"] == "t1"
    assert doc["payload"] == doc["parameters"] == {"ip_address": IP} and doc["status"] == "pending"
    assert doc["triggered_by"] == STAMP_SOURCE == "autonomous_ops"
    assert doc["autonomy"] == {"actionId": action_id, "tenantId": "t1", "kind": "action"} and doc["created_at"]
    assert (await ledger.get(live, "t1", action_id))["instructionIds"] == [result["task_id"]]
    assert await live.agent_instructions.count_documents({}) == 1


async def test_an_approved_row_becomes_dispatching_when_executed(live):
    d = await gate.decide(live, _req("t1", "203.0.113.20", actions=("isolate_host",)), master_shadow=False)
    assert d.state == "awaiting_approval"
    decided = {"ip_address": "203.0.113.20"}     # what the row was decided with (81-15)
    refused = await gate.execute(live, "t1", d.action_id, command="isolate_host", agent_id="a1", params=decided)
    assert refused == {"status": "refused", "reason": "not_dispatchable"}
    assert await ledger.transition(live, "t1", d.action_id, ("awaiting_approval",), "approved") is not None
    assert (await gate.execute(live, "t1", d.action_id, command="isolate_host", agent_id="a1",
                               params=decided))["status"] == "queued"
    assert (await ledger.get(live, "t1", d.action_id))["state"] == "dispatching"


@pytest.mark.parametrize("state", ["shadow", "refused", "denied", "expired", "suggested", "awaiting_approval"])
async def test_execute_refuses_rows_that_are_not_dispatchable(live, state):
    row = await ledger.create_intent(live, _row("t1", state, dedupe_key=f"k-{state}"))
    out = await gate.execute(live, "t1", row["id"], command="block_ip", agent_id="a1", params={})
    assert out == {"status": "refused", "reason": "not_dispatchable"}
    out = await gate.execute_response_task(live, "t1", row["id"], action="block_ip", agent_id="a1", params={})
    assert out == {"status": "refused", "reason": "not_dispatchable"}
    assert await live.agent_instructions.count_documents({}) == 0
    assert await live.response_tasks.count_documents({}) == 0


async def test_execute_refuses_unknown_rows_other_tenants_and_bad_kinds(live):
    action_id = await _dispatching(live)
    assert (await gate.execute(live, "t1", "AO-nope", command="x", agent_id="a1", params={}))["reason"] == "not_found"
    assert (await gate.execute(live, "t2", action_id, command="x", agent_id="a1", params={}))["reason"] == "not_found"
    assert (await gate.execute(live, "t1", action_id, command="x", agent_id="a1", params={},
                               kind="bogus"))["reason"] == "invalid_kind"
    assert await live.agent_instructions.count_documents({}) == 0


def _decided_row(state, ip=IP, **kw):
    """A row created directly, carrying the plan it was 'decided' with: block_ip on ``ip``, its
    compensation (unblock_ip) and the recorded undo."""
    step = {"command": "block_ip", "params": {"ip_address": ip}}
    return _row("t1", state, dedupe_key=f"k-{state}-{ip}", actions=["block_ip"], command="block_ip",
                targets=["a1"], params={"ip_address": ip}, steps=[step],
                rollback=[{"command": "unblock_ip", "params": {"ip_address": ip}}],
                undo={"available": True, "action": "unblock_ip", "params": {"ip_address": ip}}, **kw)


async def test_kinds_are_dispatched_from_their_own_states(live):
    a = (await ledger.create_intent(live, _decided_row("dispatching")))["id"]
    probe = dict(command="scan_ip", agent_id="a1", params={})
    comp = dict(command="unblock_ip", agent_id="a1", params={"ip_address": IP})
    assert (await gate.execute(live, "t1", a, kind="probe", **probe))["status"] == "queued"      # dispatching
    assert (await gate.execute(live, "t1", a, kind="undo", **comp))["reason"] == "not_dispatchable"
    assert (await gate.execute(live, "t1", a, kind="compensate", **comp))["status"] == "queued"   # dispatching
    await ledger.transition(live, "t1", a, ("dispatching",), "executed")
    assert (await gate.execute(live, "t1", a, kind="probe", **probe))["status"] == "queued"      # executed
    assert (await gate.execute(live, "t1", a, kind="action", **probe))["reason"] == "not_dispatchable"
    await ledger.transition(live, "t1", a, ("executed",), "undone")
    assert (await gate.execute(live, "t1", a, kind="undo", **comp))["status"] == "queued"
    assert (await gate.execute(live, "t1", a, kind="probe", **probe))["reason"] == "not_dispatchable"
    b = (await ledger.create_intent(live, _decided_row("dispatching", ip="203.0.113.21")))["id"]
    await ledger.transition(live, "t1", b, ("dispatching",), "failed")
    comp_b = dict(comp, params={"ip_address": "203.0.113.21"})
    assert (await gate.execute(live, "t1", b, kind="compensate", **comp_b))["status"] == "queued"
    kinds = {d["autonomy"]["kind"] async for d in live.agent_instructions.find({})}
    assert kinds == {"probe", "compensate", "undo"}


@pytest.mark.parametrize("stop_kind", ["platform", "tenant", "unreadable_platform"])
async def test_a_stop_holds_back_actions_and_probes_but_not_undo_or_compensate(live, stop_kind):
    """D-12: putting things back still works during a stop."""
    a = await _dispatching(live, ip="203.0.113.30")
    u = await _dispatching(live, ip="203.0.113.31")
    await ledger.transition(live, "t1", u, ("dispatching",), "undone")
    c = await _dispatching(live, ip="203.0.113.32")
    await ledger.transition(live, "t1", c, ("dispatching",), "failed")
    ips = {a: "203.0.113.30", u: "203.0.113.31", c: "203.0.113.32"}
    kw = dict(command="unblock_ip", agent_id="a1")
    patches = []
    if stop_kind == "platform":
        await seed_platform_stop(live)
    elif stop_kind == "tenant":
        await seed_tenant(live, "t1", shadow=False, stop={"active": True, "scope": "tenant"})
    else:
        patches.append(patch.object(settings, "platform_stop", AsyncMock(side_effect=RuntimeError("down"))))
    for p in patches:
        p.start()
    try:
        held = dict(command="block_ip", agent_id="a1", params={"ip_address": ips[a]})
        assert (await gate.execute(live, "t1", a, **held))["reason"] == "stopped"
        assert (await gate.execute(live, "t1", a, kind="probe", command="scan_ip", agent_id="a1",
                                   params={}))["reason"] == "stopped"
        assert (await gate.execute_response_task(live, "t1", a, action="block_ip", agent_id="a1",
                                                 params={"ip_address": ips[a]}))["reason"] == "stopped"
        assert (await gate.execute(live, "t1", u, kind="undo", params={"ip_address": ips[u]}, **kw))["status"] == "queued"
        assert (await gate.execute(live, "t1", c, kind="compensate", params={"ip_address": ips[c]},
                                   **kw))["status"] == "queued"
    finally:
        for p in patches:
            p.stop()
    assert await live.response_tasks.count_documents({}) == 0


async def test_an_inactive_stop_does_not_hold_anything_back(live):
    await seed_platform_stop(live, active=False)
    await seed_tenant(live, "t1", shadow=False, stop={"active": False, "scope": "tenant"})
    a = await _dispatching(live)
    assert (await gate.execute(live, "t1", a, command="block_ip", agent_id="a1",
                               params={"ip_address": IP}))["status"] == "queued"


async def test_execute_response_task_writes_one_stamped_task(live):
    a = await _dispatching(live)
    out = await gate.execute_response_task(live, "t1", a, action="block_ip", agent_id="a1",
                                           params={"ip_address": IP}, playbook_execution_id="PBX-1")
    assert out["status"] == "queued"
    doc = await live.response_tasks.find_one({"task_id": out["task_id"]}, {"_id": 0})
    assert doc["agent_id"] == "a1" and doc["action"] == "block_ip" and doc["params"] == {"ip_address": IP}
    assert doc["tenantId"] == "t1" and doc["status"] == "queued" and doc["triggered_by"] == STAMP_SOURCE
    assert doc["autonomy"] == {"actionId": a, "tenantId": "t1", "kind": "action"}
    assert doc["playbook_execution_id"] == "PBX-1"
    assert (await ledger.get(live, "t1", a))["instructionIds"] == [out["task_id"]]
    assert await live.agent_instructions.count_documents({}) == 0


async def test_open_dedupe_index_allows_one_open_decision_per_key(live):
    first = await gate.decide(live, _req(key="k1"), master_shadow=False)
    second = await gate.decide(live, _req(key="k1"), master_shadow=False)
    assert first.recorded and (second.outcome, second.reason, second.recorded) == ("refuse", "duplicate", False)
    assert await live.autonomy_actions.count_documents({"tenantId": "t1"}) == 1
    await ledger.transition(live, "t1", first.action_id, ("dispatching",), "executed")
    assert (await gate.decide(live, _req(key="k1"), master_shadow=False)).recorded


async def test_record_control_writes_a_control_row_and_an_audit_event(live):
    row = await ledger.record_control(live, "t1", "stop_pressed", scope="tenant", reason="drill",
                                      actor={"username": "alice", "display": "Alice", "tier": "tenant"})
    assert (row["kind"], row["state"], row["controlEvent"], row["scope"]) == ("control", "recorded", "stop_pressed", "tenant")
    assert row["actor"]["username"] == "alice" and row["reasonText"] == "drill"
    assert [e["action"] for e in await _events(live)] == ["autonomous_ops.stop_pressed"]
    assert (await ledger.counts(live, "t1")) == {k: 0 for k in ledger.BUCKET_STATES}      # control is in no bucket
    assert [i["id"] for i in (await ledger.list_actions(live, "t1"))["items"]] == [row["id"]]
    assert (await ledger.list_actions(live, "t1", bucket="done"))["items"] == []


async def test_an_empty_tenant_lists_nothing_and_counts_zero(live):
    page = await ledger.list_actions(live, "nobody")
    assert page == {"items": [], "nextCursor": None}
    assert await ledger.counts(live, "nobody") == {"pending": 0, "done": 0, "undone": 0, "failed": 0,
                                                   "refused": 0, "suggested": 0, "simulation": 0}
    with pytest.raises(ValueError):
        await ledger.list_actions(live, "t1", bucket="bogus")
    with pytest.raises(ValueError):
        await ledger.list_actions(live, "t1", cursor="not-a-cursor")


async def test_rows_sharing_a_created_at_page_in_a_stable_order(live):
    """Edge GATE-07 ordering: createdAt desc then id desc, no repeats or gaps across pages."""
    when = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    for n in range(5):
        d = await gate.decide(live, _req(ip=f"203.0.113.{40 + n}"), master_shadow=True, now=when)
        assert d.state == "shadow"
    await gate.decide(live, _req(ip="203.0.113.99"), master_shadow=True, now=when + timedelta(seconds=1))
    seen, cursor = [], None
    for _ in range(5):
        page = await ledger.list_actions(live, "t1", bucket="simulation", limit=2, cursor=cursor)
        seen += [i["id"] for i in page["items"]]
        cursor = page["nextCursor"]
        if cursor is None:
            break
    assert len(seen) == 6 and len(set(seen)) == 6
    full = await ledger.list_actions(live, "t1", bucket="simulation", limit=50)
    assert seen == [i["id"] for i in full["items"]]
    same_time = [i for i in full["items"] if i["createdAt"] == when]
    assert [i["id"] for i in same_time] == sorted((i["id"] for i in same_time), reverse=True)
    assert full["items"][0]["createdAt"] == when + timedelta(seconds=1)
    assert (await ledger.counts(live, "t1"))["simulation"] == 6


async def test_buckets_map_states_and_counts_agree(live):
    states = {"pending": ["awaiting_approval", "approved", "dispatching"], "done": ["executed", "verified"],
              "undone": ["undone", "rolled_back"], "failed": ["failed"],
              "refused": ["refused", "denied", "expired", "cancelled_by_stop"], "suggested": ["suggested"],
              "simulation": ["shadow"]}
    for bucket, names in states.items():
        for n, state in enumerate(names):
            await ledger.create_intent(live, _row("t1", state, dedupe_key=f"{state}"))
    counts = await ledger.counts(live, "t1")
    assert counts == {b: len(n) for b, n in states.items()}
    for bucket, names in states.items():
        items = (await ledger.list_actions(live, "t1", bucket=bucket))["items"]
        assert sorted(i["state"] for i in items) == sorted(names)


async def test_auto_counts_exclude_shadow_control_and_the_boundary(live):
    since = datetime.now(timezone.utc) - timedelta(minutes=30)
    old = since - timedelta(seconds=1)
    await ledger.create_intent(live, _row("t1", "executed", autoDispatched=True, createdAt=since + timedelta(seconds=1),
                                          finishedAt=since + timedelta(minutes=1), dedupe_key="n1"))
    await ledger.create_intent(live, _row("t1", "dispatching", autoDispatched=True, createdAt=since, dedupe_key="n2"))
    await ledger.create_intent(live, _row("t1", "executed", autoDispatched=True, createdAt=old, finishedAt=old, dedupe_key="n3"))
    await ledger.create_intent(live, _row("t1", "shadow", autoDispatched=True, createdAt=since + timedelta(minutes=1)))
    await ledger.create_intent(live, _row("t1", "awaiting_approval", autoDispatched=False, dedupe_key="n4"))
    await ledger.record_control(live, "t1", "stop_pressed", scope="tenant", actor={}, reason=None)
    assert await ledger.count_auto_since(live, "t1", since) == 1          # strictly after
    assert await ledger.count_auto_since(live, "t2", since) == 0
    recent = await ledger.recent_finished_auto(live, "t1", n=3)
    assert [r["dedupeKey"] for r in recent] == ["n1", "n3"]               # newest finish first, unfinished excluded
    assert all(r["finishedAt"].tzinfo is not None for r in recent)


async def test_timestamps_are_aware_datetimes(live):
    d = await gate.decide(live, _req(), master_shadow=False)
    row = await live.autonomy_actions.find_one({"id": d.action_id})
    assert isinstance(row["createdAt"], datetime) and isinstance(row["updatedAt"], datetime)
    got = await ledger.get(live, "t1", d.action_id)
    assert got["createdAt"].tzinfo is not None and "_id" not in got


def test_decision_records_sit_outside_every_retention_path():
    """GATE-07 retention."""
    assert DECISION_RETENTION_FLOOR_DAYS >= 365
    assert PROTECTED_COLLECTIONS == {"autonomy_actions", "autonomy_settings", "autonomy_never_touch", "autonomy_golive_checks"}
    for rel in ("retention_service.py", "retention_endpoints.py", "audit_ledger.py"):
        text = open(os.path.join(BACKEND, rel), encoding="utf-8").read()
        for name in PROTECTED_COLLECTIONS:
            assert name not in text, f"{rel} names {name}"
    assert "purge_expired" in open(os.path.join(BACKEND, "audit_ledger.py"), encoding="utf-8").read()


async def test_fake_ledger_and_permissive_gate_serve_legacy_tests():
    fake = FakeLedger()
    row = await fake.create_intent(None, {"tenantId": "t1", "state": "approved"})
    assert await fake.get(None, "t2", row["id"]) is None
    assert await fake.transition(None, "t1", row["id"], ("approved",), "dispatching") is not None
    assert await fake.transition(None, "t1", row["id"], ("approved",), "dispatching") is None
    with permissive_gate("needs_approval") as stack:
        req = gate.ActionRequest(tenant_id="t1", kind="security", origin="x", actions=["block_ip"], targets=["a1"],
                                 params={}, dedupe_key="k")
        d = await gate.decide(None, req)
        assert (d.outcome, d.state, d.recorded) == ("needs_approval", "awaiting_approval", True)
        assert (await gate.ledger.get(None, "t1", d.action_id))["state"] == "awaiting_approval"
        assert await settings.platform_stop(None) is None
        assert (await settings.load(None, "t1")).eligible is True
        assert stack.ledger.rows
    with permissive_gate("allow_auto", shadow=True):
        d = await gate.decide(None, req)
        assert (d.state, d.would_have, d.shadow) == ("shadow", "allow_auto", True)
