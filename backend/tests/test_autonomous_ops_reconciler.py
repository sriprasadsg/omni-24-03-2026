"""Autonomous Ops reconciler (Phase 81, plan 81-04, GATE-11 / D-13 / D-16).
Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py.

Value: protects=overdue cards expire even during a stop, dispatched rows follow what the agent
reported, a stuck dispatch is failed instead of blocking its key forever, one runner at a time,
one tenant's failure never stops the others, the tenant ContextVar is never left set;
fails_when=a stale card survives a stop, a failed instruction stays "dispatching", two runners
tick at once, or the tenant ContextVar leaks out of a tick; no_claim=the live loop cadence and
the startup wiring on a running backend.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tenant_context
from autonomous_ops import APPROVAL_TTL, approvals, breaker, gate, ledger, messages, protected, reconciler
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_agent, seed_platform_stop, seed_tenant

APPROVER = {"username": "alice", "display": "Alice", "tier": "tenant"}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv("AUTONOMOUS_REMEDIATION_DRY_RUN", raising=False)
    monkeypatch.delenv("AUTONOMOUS_OPS_STUCK_DISPATCH_MIN", raising=False)
    monkeypatch.delenv("AUTONOMOUS_OPS_NO_RESULT_MIN", raising=False)
    protected.cache_clear()


@pytest.fixture
async def live(mongo_db):
    await ledger.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1", shadow=False)
    await seed_agent(mongo_db, "t1", "a1")
    return mongo_db


def _req(tenant="t1", action="block_ip", ip="203.0.113.7", target="a1"):
    return gate.ActionRequest(tenant_id=tenant, kind="security", origin="test", actions=[action], targets=[target],
                              params={"ip_address": ip}, dedupe_key=f"{tenant}|{action}|{ip}",
                              reason={"ruleId": "test", "inputs": {}})


async def _dispatched(db, ip, tenant="t1", target="a1", status=None):
    """An automatic row that has been dispatched; its instruction gets ``status`` when given."""
    d = await gate.decide(db, _req(tenant, ip=ip, target=target), master_shadow=False)
    assert d.state == "dispatching", d
    out = await gate.execute(db, tenant, d.action_id, command="block_ip", agent_id=target, params={"ip_address": ip})
    if status:
        await db.agent_instructions.update_one({"id": out["task_id"]}, {"$set": {"status": status}})
    return d.action_id, out["task_id"]


async def _state(db, action_id, tenant="t1"):
    return (await ledger.get(db, tenant, action_id))["state"]


async def _age(db, action_id, minutes):
    old = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    await db.autonomy_actions.update_one({"id": action_id}, {"$set": {"updatedAt": old}})


async def test_tracer_empty_database_ticks_cleanly(mongo_db):
    """Edge GATE-11 empty."""
    assert tenant_context.get_tenant_id() is None
    assert await reconciler.tick(mongo_db) == {"expired": 0, "executed": 0, "failed": 0, "tripped": 0}
    assert tenant_context.get_tenant_id() is None
    for name in await mongo_db.list_collection_names():
        assert await mongo_db[name].count_documents({}) == 0, name


async def test_overdue_cards_expire_also_while_a_stop_is_on(live):
    d = await gate.decide(live, _req(action="isolate_host"), master_shadow=False)
    assert d.state == "awaiting_approval"
    await seed_platform_stop(live)
    later = datetime.now(timezone.utc) + APPROVAL_TTL + timedelta(seconds=1)
    assert (await reconciler.tick(live, now=later))["expired"] == 1
    assert await _state(live, d.action_id) == "expired"
    assert await live.agent_instructions.count_documents({}) == 0
    assert tenant_context.get_tenant_id() is None


async def test_cards_that_are_not_overdue_are_left_alone(live):
    d = await gate.decide(live, _req(action="isolate_host"), master_shadow=False)
    assert (await reconciler.tick(live))["expired"] == 0
    assert await _state(live, d.action_id) == "awaiting_approval"


@pytest.mark.parametrize("status,expected", [("COMPLETED", "executed"), ("SUCCESS", "executed"),
                                             ("completed", "executed"), ("FAILURE", "failed"),
                                             ("FAILED", "failed"), ("REFUSED", "failed")])
async def test_dispatched_rows_follow_the_instruction_status(live, status, expected):
    action_id, _ = await _dispatched(live, "203.0.113.10", status=status)
    counts = await reconciler.tick(live)
    assert await _state(live, action_id) == expected
    assert counts["executed" if expected == "executed" else "failed"] == 1
    row = await ledger.get(live, "t1", action_id)
    assert row["finishedAt"] is not None and row["result"]["instructionStatus"] == status.lower()
    if expected == "failed":
        assert row["reasonCode"] == "agent_failed"


async def test_pending_and_sent_instructions_are_left_while_recent(live):
    pending, _ = await _dispatched(live, "203.0.113.11")
    sent, _ = await _dispatched(live, "203.0.113.12", status="sent")
    assert (await reconciler.tick(live))["failed"] == 0
    assert await _state(live, pending) == "dispatching" and await _state(live, sent) == "dispatching"


async def test_undelivered_instruction_older_than_the_limit_fails_as_not_delivered(live, monkeypatch):
    stale, _ = await _dispatched(live, "203.0.113.13")
    fresh, _ = await _dispatched(live, "203.0.113.14")
    await _age(live, stale, 31)
    await _age(live, fresh, 29)
    assert (await reconciler.tick(live))["failed"] == 1
    assert await _state(live, stale) == "failed" and await _state(live, fresh) == "dispatching"
    assert (await ledger.get(live, "t1", stale))["reasonCode"] == "not_delivered"
    monkeypatch.setenv("AUTONOMOUS_OPS_STUCK_DISPATCH_MIN", "5")
    await _age(live, fresh, 6)
    assert (await reconciler.tick(live))["failed"] == 1
    assert await _state(live, fresh) == "failed"


async def test_tracer_picked_up_but_silent_instruction_fails_no_result_and_frees_the_slot(live):
    """WR-01: a sent instruction that never reports fails no_result after the bound."""
    action, _ = await _dispatched(live, "203.0.113.30", status="sent")
    await _age(live, action, 25 * 60)
    assert (await reconciler.tick(live))["failed"] == 1
    row = await ledger.get(live, "t1", action)
    assert row["state"] == "failed" and row["reasonCode"] == "no_result"
    assert row["reasonText"] == messages.REASON_TEXT["no_result"]
    again = await gate.decide(live, _req(ip="203.0.113.30"), master_shadow=False)
    assert again.state == "dispatching" and again.action_id != action


async def test_no_result_waits_for_its_own_bound(live):
    delivered, _ = await _dispatched(live, "203.0.113.31", status="delivered")
    sent, _ = await _dispatched(live, "203.0.113.32", status="sent")
    pending, _ = await _dispatched(live, "203.0.113.33")
    await _age(live, delivered, 23 * 60)
    await _age(live, sent, 31)
    await _age(live, pending, 31)
    assert (await reconciler.tick(live))["failed"] == 1
    assert await _state(live, delivered) == "dispatching" and await _state(live, sent) == "dispatching"
    assert (await ledger.get(live, "t1", pending))["reasonCode"] == "not_delivered"


async def test_no_result_cutoff_is_inclusive_to_the_second(live):
    """Edge GATE-07 adjacency."""
    at_bound, _ = await _dispatched(live, "203.0.113.34", status="sent")
    younger, _ = await _dispatched(live, "203.0.113.35", status="sent")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    await live.autonomy_actions.update_one({"id": at_bound}, {"$set": {"updatedAt": now - timedelta(minutes=1440)}})
    await live.autonomy_actions.update_one(
        {"id": younger}, {"$set": {"updatedAt": now - timedelta(minutes=1440) + timedelta(seconds=1)}})
    assert (await reconciler.tick(live, now=now))["failed"] == 1
    assert await _state(live, at_bound) == "failed" and await _state(live, younger) == "dispatching"


@pytest.mark.parametrize("status", ["in_progress", "running"])
async def test_unrecognised_status_fails_closed_after_the_bound(live, status):
    action, _ = await _dispatched(live, "203.0.113.36", status=status)
    await _age(live, action, 25 * 60)
    assert (await reconciler.tick(live))["failed"] == 1
    assert (await ledger.get(live, "t1", action))["reasonCode"] == "no_result"


async def test_no_result_bound_env_override_fallback_and_floor(live, monkeypatch):
    action, _ = await _dispatched(live, "203.0.113.37", status="sent")
    await _age(live, action, 91)
    assert (await reconciler.tick(live))["failed"] == 0
    monkeypatch.setenv("AUTONOMOUS_OPS_NO_RESULT_MIN", "90")
    assert reconciler._no_result_after() == timedelta(minutes=90)
    assert (await reconciler.tick(live))["failed"] == 1
    for bad in ("abc", "0", "-5"):
        monkeypatch.setenv("AUTONOMOUS_OPS_NO_RESULT_MIN", bad)
        assert reconciler._no_result_after() == timedelta(minutes=1440)
    monkeypatch.setenv("AUTONOMOUS_OPS_NO_RESULT_MIN", "5")
    assert reconciler._no_result_after() == reconciler._stuck_after()


async def test_no_result_move_does_not_overwrite_a_concurrent_agent_result(live):
    """Edge GATE-11 adjacency: the updatedAt bound is in the compare-and-set."""
    action, task = await _dispatched(live, "203.0.113.38", status="sent")
    await _age(live, action, 25 * 60)
    real = ledger.transition

    async def racing(db, tenant_id, action_id, from_states, to_state, **kw):
        if kw.get("reasonCode") == "no_result":
            await db.autonomy_actions.update_one({"id": action_id}, {"$set": {"updatedAt": datetime.now(timezone.utc)}})
        return await real(db, tenant_id, action_id, from_states, to_state, **kw)

    with patch.object(ledger, "transition", racing):
        assert (await reconciler.tick(live))["failed"] == 0
    assert await _state(live, action) == "dispatching"


async def test_three_agent_failures_trip_the_breaker(live):
    """Phase 83 (83-08) moved this case from silent instructions to ones the host reported as failed: an
    instruction nobody answered is plumbing and is transparent to the breaker (see the next test)."""
    ids = [(await _dispatched(live, f"203.0.113.{40 + i}", status="failed"))[0] for i in range(3)]
    out = await reconciler.tick(live)
    assert out["failed"] == 3 and out["tripped"] == 1
    assert (await settings_load(live)).breaker is not None


async def test_three_no_result_failures_do_not_trip_the_breaker(live):
    """Phase 83 (83-08, RESP-10): a host that never answered is not a failed action."""
    ids = [(await _dispatched(live, f"203.0.113.{50 + i}", status="sent"))[0] for i in range(3)]
    for action in ids:
        await _age(live, action, 25 * 60)
    out = await reconciler.tick(live)
    assert out["failed"] == 3 and out["tripped"] == 0
    assert (await settings_load(live)).breaker is None
    assert {(await ledger.get(live, "t1", a))["reasonCode"] for a in ids} == {"no_result"}


async def settings_load(db):
    from autonomous_ops import settings
    return await settings.load(db, "t1")


async def test_dispatching_row_with_no_instruction_at_all_fails_once_old(live):
    d = await gate.decide(live, _req(ip="203.0.113.15"), master_shadow=False)
    assert d.state == "dispatching"
    assert (await reconciler.tick(live))["failed"] == 0
    await _age(live, d.action_id, 45)
    assert (await reconciler.tick(live))["failed"] == 1
    assert (await ledger.get(live, "t1", d.action_id))["reasonCode"] == "not_delivered"


async def test_response_task_outcomes_are_followed_too(live):
    d = await gate.decide(live, _req(ip="203.0.113.16"), master_shadow=False)
    out = await gate.execute_response_task(live, "t1", d.action_id, action="block_ip", agent_id="a1",
                                           params={"ip_address": "203.0.113.16"})
    assert (await reconciler.tick(live))["executed"] == 0           # still queued
    await live.response_tasks.update_one({"task_id": out["task_id"]}, {"$set": {"status": "executed"}})
    assert (await reconciler.tick(live))["executed"] == 1
    assert await _state(live, d.action_id) == "executed"


async def test_another_tenants_instruction_with_the_same_id_is_never_read(live):
    action_id, task_id = await _dispatched(live, "203.0.113.17")
    await live.agent_instructions.update_one({"id": task_id}, {"$set": {"status": "SUCCESS", "tenantId": "t2"}})
    assert (await reconciler.tick(live))["executed"] == 0
    assert await _state(live, action_id) == "dispatching"


async def test_the_breaker_is_asked_once_per_tenant_whose_rows_changed(live):
    await _dispatched(live, "203.0.113.20", status="FAILURE")
    await _dispatched(live, "203.0.113.21", status="SUCCESS")
    await seed_tenant(live, "t2", shadow=False)
    await seed_agent(live, "t2", "b1")
    await _dispatched(live, "203.0.113.20", tenant="t2", target="b1")      # nothing changes for t2
    with patch.object(breaker, "evaluate", AsyncMock(return_value=False)) as ev:
        await reconciler.tick(live)
    assert [c.args[1] for c in ev.await_args_list] == ["t1"]


async def test_three_failed_instructions_trip_the_breaker_end_to_end(live):
    for i in range(3):
        await _dispatched(live, f"203.0.113.3{i}", status="FAILURE")
    with patch("autonomous_ops.breaker.notify.notify", AsyncMock()) as notice:
        counts = await reconciler.tick(live)
    assert counts["failed"] == 3 and counts["tripped"] == 1
    assert (await live.autonomy_settings.find_one({"tenantId": "t1"}))["level"] == "suggest"
    notice.assert_awaited_once()
    # the reconciler never restores a tripped breaker
    with patch("autonomous_ops.breaker.notify.notify", AsyncMock()):
        assert (await reconciler.tick(live))["tripped"] == 0
    assert (await live.autonomy_settings.find_one({"tenantId": "t1"}))["level"] == "suggest"


async def test_tenants_are_processed_in_sorted_order_and_one_failure_does_not_stop_the_rest(live):
    for tenant in ("t-c", "t-a", "t-b"):
        await seed_tenant(live, tenant, shadow=False)
        await seed_agent(live, tenant, f"ag-{tenant}")
        await gate.decide(live, _req(tenant, action="isolate_host", target=f"ag-{tenant}"), master_shadow=False)
    seen = []
    real = approvals.expire_due

    async def spy(db, *, now=None, tenant_id=None):
        seen.append((tenant_id, tenant_context.get_tenant_id()))
        if tenant_id == "t-a":
            raise RuntimeError("boom")
        return await real(db, now=now, tenant_id=tenant_id)

    later = datetime.now(timezone.utc) + APPROVAL_TTL + timedelta(seconds=1)
    with patch.object(approvals, "expire_due", spy):
        counts = await reconciler.tick(live, now=later)
    assert seen == [("t-a", "t-a"), ("t-b", "t-b"), ("t-c", "t-c")]       # sorted; scoped to the tenant
    assert counts["expired"] == 2
    assert tenant_context.get_tenant_id() is None


async def test_a_lost_lock_stops_the_pass_between_tenants(live):
    for tenant in ("t-a", "t-b"):
        await seed_tenant(live, tenant, shadow=False)
        await seed_agent(live, tenant, f"ag-{tenant}")
        await gate.decide(live, _req(tenant, action="isolate_host", target=f"ag-{tenant}"), master_shadow=False)
    later = datetime.now(timezone.utc) + APPROVAL_TTL + timedelta(seconds=1)
    polls = iter([False, True, True])
    counts = await reconciler.tick(live, now=later, lost=lambda: next(polls))
    assert counts["expired"] == 1


async def test_only_one_runner_ticks_at_a_time(live):
    entered = []

    async def slow(db, *, now=None, lost=None):
        entered.append(1)
        await asyncio.sleep(0.4)
        return {"expired": 0, "executed": 0, "failed": 0, "tripped": 0}

    with patch.object(reconciler, "tick", slow):
        results = await asyncio.gather(reconciler.run_once(live), reconciler.run_once(live))
    assert len(entered) == 1 and results.count(None) == 1
    # the lock is released afterwards, so the next runner proceeds
    with patch.object(reconciler, "tick", slow):
        assert await reconciler.run_once(live) is not None
    assert await live["_distributed_locks"].count_documents({"_id": reconciler.LOCK_NAME}) == 0


async def test_a_held_lock_blocks_the_runner_without_touching_the_ledger(live):
    from distributed_lock import acquire_lock
    from types import SimpleNamespace
    assert await acquire_lock(SimpleNamespace(_db=live), reconciler.LOCK_NAME, ttl_seconds=30)
    d = await gate.decide(live, _req(action="isolate_host"), master_shadow=False)
    later = datetime.now(timezone.utc) + APPROVAL_TTL + timedelta(seconds=1)
    assert await reconciler.run_once(live, now=later) is None
    assert await _state(live, d.action_id) == "awaiting_approval"


async def test_the_loop_reads_its_interval_from_the_environment(monkeypatch):
    assert reconciler._interval() == 60 and reconciler._stuck_after() == timedelta(minutes=30)
    monkeypatch.setenv("AUTONOMOUS_OPS_RECONCILE_INTERVAL_SEC", "5")
    monkeypatch.setenv("AUTONOMOUS_OPS_STUCK_DISPATCH_MIN", "x")
    assert reconciler._interval() == 5 and reconciler._stuck_after() == timedelta(minutes=30)


async def test_the_loop_survives_a_failing_pass_and_keeps_going(monkeypatch):
    calls = []

    async def flaky(db, **kw):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("down")
        raise asyncio.CancelledError

    monkeypatch.setenv("AUTONOMOUS_OPS_RECONCILE_INTERVAL_SEC", "0.01")
    with patch("database.get_database", lambda: object()), patch.object(reconciler, "run_once", flaky):
        with pytest.raises(asyncio.CancelledError):
            await reconciler.reconciler_loop()
    assert len(calls) == 2
