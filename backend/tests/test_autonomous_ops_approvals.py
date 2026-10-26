"""Autonomous Ops approvals (Phase 81, plan 81-04, GATE-10 / D-12 / D-13 / D-16).
Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py.

Value: protects=an approval card dispatches exactly once, never after its 24 hour clock, never
during a stop, and only after the target is re-checked; undo still works during a stop;
fails_when=two concurrent approves write two instructions, an expired or frozen card
dispatches, a moved or protected target is acted on, or undo is blocked by a stop;
no_claim=the HTTP routes (plan 81-09) and the remediation dispatcher (plan 81-08).
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import APPROVAL_TTL, approvals, gate, ledger, protected, settings
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_agent, seed_platform_stop, seed_tenant

IP = "203.0.113.7"
APPROVER = {"username": "alice", "display": "Alice", "tier": "tenant"}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv("AUTONOMOUS_REMEDIATION_DRY_RUN", raising=False)
    protected.cache_clear()


@pytest.fixture
async def live(mongo_db):
    await ledger.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1", shadow=False)
    await seed_agent(mongo_db, "t1", "a1")
    return mongo_db


def _req(tenant="t1", action="isolate_host", target="a1", ip=None, key=None, dispatcher="instruction"):
    params = {"ip_address": ip} if ip else {}
    return gate.ActionRequest(tenant_id=tenant, kind="security", origin="test", actions=[action], targets=[target],
                              params=params, dedupe_key=key or f"{tenant}|{action}|{target}|{ip}",
                              reason={"ruleId": "test", "inputs": {}}, dispatcher=dispatcher)


async def _card(db, **kw):
    d = await gate.decide(db, _req(**kw), master_shadow=False)
    assert d.state == "awaiting_approval", d
    return d.action_id


async def _events(db, tenant="t1"):
    return [e["action"] async for e in db.audit_logs.find({"tenantId": tenant}).sort("seq", 1)]


async def test_tracer_approve_dispatches_one_stamped_instruction(live):
    action_id = await _card(live)
    row = await ledger.get(live, "t1", action_id)
    assert row["approval"]["expiresAt"] - row["createdAt"] == APPROVAL_TTL

    out = await approvals.approve(live, "t1", action_id, approver=APPROVER)

    assert out["status"] == "dispatched" and out["dispatch"]["status"] == "queued"
    instructions = await live.agent_instructions.find({}).to_list(10)
    assert len(instructions) == 1
    assert instructions[0]["type"] == "isolate_host" and instructions[0]["tenantId"] == "t1"
    assert instructions[0]["autonomy"]["actionId"] == action_id
    row = await ledger.get(live, "t1", action_id)
    assert row["state"] == "dispatching"
    assert row["approval"]["approver"] == APPROVER and row["approval"]["decidedAt"] is not None
    events = [e for e in await _events(live) if e in ("autonomous_ops.approved", "autonomous_ops.dispatching")]
    assert events == ["autonomous_ops.approved", "autonomous_ops.dispatching"]


@pytest.mark.parametrize("callers", [2, 5])
async def test_concurrent_approves_dispatch_exactly_once(live, callers):
    """Edge GATE-10: gather race on a real database."""
    action_id = await _card(live)
    results = await asyncio.gather(*(approvals.approve(live, "t1", action_id, approver=APPROVER)
                                     for _ in range(callers)))
    assert sorted(r["status"] for r in results) == ["already_handled"] * (callers - 1) + ["dispatched"]
    assert await live.agent_instructions.count_documents({}) == 1
    assert len([e for e in await _events(live) if e == "autonomous_ops.approved"]) == 1


async def test_second_approve_after_the_first_is_already_handled(live):
    action_id = await _card(live)
    assert (await approvals.approve(live, "t1", action_id, approver=APPROVER))["status"] == "dispatched"
    assert (await approvals.approve(live, "t1", action_id, approver=APPROVER))["status"] == "already_handled"
    assert await live.agent_instructions.count_documents({}) == 1


async def test_a_suggested_row_can_be_approved(live):
    d = await gate.suggest(live, _req(action="isolate_host"), master_shadow=False)
    assert d.state == "suggested"
    assert (await approvals.approve(live, "t1", d.action_id, approver=APPROVER))["status"] == "dispatched"


async def test_other_tenants_row_is_not_found(live):
    await seed_tenant(live, "t2", shadow=False)
    action_id = await _card(live)
    assert (await approvals.approve(live, "t2", action_id, approver=APPROVER))["status"] == "not_found"
    assert (await approvals.approve(live, "t1", "AO-missing", approver=APPROVER))["status"] == "not_found"
    assert (await ledger.get(live, "t1", action_id))["state"] == "awaiting_approval"
    assert await live.agent_instructions.count_documents({}) == 0


async def _refused(db, action_id, code):
    out = await approvals.approve(db, "t1", action_id, approver=APPROVER)
    assert out == {"status": "refused", "reason": code}
    row = await ledger.get(db, "t1", action_id)
    assert row["state"] == "refused" and row["reasonCode"] == code
    assert await db.agent_instructions.count_documents({}) == 0


async def test_deleted_target_is_refused_no_target(live):
    action_id = await _card(live)
    await live.agents.delete_one({"id": "a1"})
    await _refused(live, action_id, "no_target")


async def test_target_moved_to_another_tenant_is_refused(live):
    action_id = await _card(live)
    await live.agents.update_one({"id": "a1"}, {"$set": {"tenantId": "t2"}})
    await _refused(live, action_id, "cross_tenant_target")


async def test_target_added_to_the_never_touch_list_is_refused(live):
    action_id = await _card(live)
    await live.agents.update_one({"id": "a1"}, {"$set": {"ipAddress": "10.77.0.5"}})
    await live.autonomy_never_touch.insert_one({"id": "nt1", "scope": "tenant", "tenantId": "t1", "kind": "ip",
                                                "value": "10.77.0.5", "note": ""})
    await _refused(live, action_id, "protected_target")


async def test_protected_ip_parameter_is_refused(live):
    d = await gate.decide(live, _req(action="block_ip", ip=IP, key="k-ip"), master_shadow=False,)
    assert d.state == "dispatching"          # block_ip is automatic; make a suggested twin
    d = await gate.suggest(live, _req(action="block_ip", ip="203.0.113.99", key="k-ip2"), master_shadow=False)
    await live.autonomy_never_touch.insert_one({"id": "nt2", "scope": "tenant", "tenantId": "t1", "kind": "ip",
                                                "value": "203.0.113.99", "note": ""})
    await _refused(live, d.action_id, "protected_target")


async def test_level_turned_off_after_the_card_was_made_is_refused(live):
    action_id = await _card(live)
    await live.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"level": "off"}})
    await _refused(live, action_id, "level_off")


async def test_untick_after_the_card_was_made_is_refused(live):
    action_id = await _card(live)
    await live.tenants.update_one({"id": "t1"}, {"$set": {"enabledFeatures": ["view:overview"]}})
    await _refused(live, action_id, "not_enabled")


async def test_unknown_dispatcher_is_refused_without_changing_the_row(live):
    action_id = await _card(live)
    await live.autonomy_actions.update_one({"id": action_id}, {"$set": {"dispatcher": "nonsense"}})
    out = await approvals.approve(live, "t1", action_id, approver=APPROVER)
    assert out == {"status": "refused", "reason": "no_dispatcher"}
    assert (await ledger.get(live, "t1", action_id))["state"] == "awaiting_approval"


async def test_registered_dispatcher_is_called_after_the_approval(live):
    calls = []

    async def fake(db, row, approver):
        calls.append((row["id"], row["state"], approver))
        return {"status": "queued", "task_id": "x"}

    approvals.register_dispatcher("fake_remediation", fake)
    try:
        action_id = await _card(live, dispatcher="fake_remediation")
        out = await approvals.approve(live, "t1", action_id, approver=APPROVER)
    finally:
        approvals._DISPATCHERS.pop("fake_remediation", None)
    assert out["status"] == "dispatched" and out["dispatch"] == {"status": "queued", "task_id": "x"}
    assert calls == [(action_id, "approved", APPROVER)]


async def test_a_dispatcher_that_raises_fails_the_row(live):
    async def boom(db, row, approver):
        raise RuntimeError("down")

    approvals.register_dispatcher("boom", boom)
    try:
        action_id = await _card(live, dispatcher="boom")
        out = await approvals.approve(live, "t1", action_id, approver=APPROVER)
    finally:
        approvals._DISPATCHERS.pop("boom", None)
    assert out == {"status": "refused", "reason": "dispatch_failed"}
    assert (await ledger.get(live, "t1", action_id))["state"] == "failed"


async def test_response_task_dispatcher_writes_a_stamped_response_task(live):
    action_id = await _card(live, dispatcher="response_task")
    out = await approvals.approve(live, "t1", action_id, approver=APPROVER)
    assert out["status"] == "dispatched"
    task = await live.response_tasks.find_one({})
    assert task["triggered_by"] == "autonomous_ops" and task["autonomy"]["actionId"] == action_id
    assert task["action"] == "isolate_host" and task["tenantId"] == "t1"


async def test_approve_during_a_stop_changes_nothing(live):
    action_id = await _card(live)
    await seed_platform_stop(live)
    assert (await approvals.approve(live, "t1", action_id, approver=APPROVER))["status"] == "stopped"
    assert (await ledger.get(live, "t1", action_id))["state"] == "awaiting_approval"
    assert await live.agent_instructions.count_documents({}) == 0


async def test_unreadable_platform_stop_counts_as_stopped(live):
    action_id = await _card(live)
    with patch.object(settings, "platform_stop", AsyncMock(side_effect=RuntimeError("db"))):
        assert (await approvals.approve(live, "t1", action_id, approver=APPROVER))["status"] == "stopped"
    assert (await ledger.get(live, "t1", action_id))["state"] == "awaiting_approval"


async def test_tenant_stop_freezes_approval_until_it_is_cleared(live):
    action_id = await _card(live)
    await live.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"stop": {"active": True}}})
    assert (await approvals.approve(live, "t1", action_id, approver=APPROVER))["status"] == "stopped"
    await live.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"stop": None}})
    assert (await approvals.approve(live, "t1", action_id, approver=APPROVER))["status"] == "dispatched"


async def test_stop_pressed_between_the_approval_and_the_dispatch_cancels_the_row(live):
    """Edge: the stop lands after the compare-and-set; nothing is written."""
    action_id = await _card(live)
    real = gate.execute

    async def pressed(db, *a, **kw):
        await seed_platform_stop(db)
        return await real(db, *a, **kw)

    with patch.object(gate, "execute", pressed):
        out = await approvals.approve(live, "t1", action_id, approver=APPROVER)
    assert out["status"] == "stopped"
    assert (await ledger.get(live, "t1", action_id))["state"] == "cancelled_by_stop"
    assert await live.agent_instructions.count_documents({}) == 0


# ---------------------------------------------------------------- Task 2: deny, expiry, undo

async def test_deny_stores_the_decision_and_works_during_a_stop(live):
    action_id = await _card(live)
    await seed_platform_stop(live)
    out = await approvals.deny(live, "t1", action_id, approver=APPROVER, reason="not now")
    assert out == {"status": "denied"}
    row = await ledger.get(live, "t1", action_id)
    assert row["state"] == "denied" and row["approval"]["approver"] == APPROVER
    assert row["approval"]["reason"] == "not now" and row["approval"]["decidedAt"] is not None
    assert (await approvals.deny(live, "t1", action_id, approver=APPROVER))["status"] == "already_handled"
    assert (await approvals.deny(live, "t2", action_id, approver=APPROVER))["status"] == "not_found"
    assert (await approvals.approve(live, "t1", action_id, approver=APPROVER))["status"] in ("already_handled", "stopped")
    assert await live.agent_instructions.count_documents({}) == 0


async def test_approve_exactly_at_expiry_is_expired_and_one_second_before_is_dispatched(live):
    first, second = await _card(live, key="k1"), await _card(live, target="a1", action="reboot_host", key="k2")
    expires = (await ledger.get(live, "t1", first))["approval"]["expiresAt"]
    out = await approvals.approve(live, "t1", first, approver=APPROVER, now=expires)
    assert out["status"] == "expired"
    assert (await ledger.get(live, "t1", first))["state"] == "expired"
    out = await approvals.approve(live, "t1", second, approver=APPROVER, now=expires - timedelta(seconds=1))
    assert out["status"] == "dispatched"
    assert await live.agent_instructions.count_documents({}) == 1


async def test_expire_due_expires_every_overdue_row_of_every_tenant(live):
    await seed_tenant(live, "t2", shadow=False)
    await seed_agent(live, "t2", "b1")
    a = await _card(live, key="k1")
    b = await gate.decide(live, _req(tenant="t2", target="b1", key="k1"), master_shadow=False)
    c = await gate.suggest(live, _req(action="reboot_host", key="k3"), master_shadow=False)
    later = datetime.now(timezone.utc) + APPROVAL_TTL + timedelta(seconds=1)
    assert await approvals.expire_due(live, now=datetime.now(timezone.utc)) == 0
    assert await approvals.expire_due(live, now=later) == 3
    assert await approvals.expire_due(live, now=later) == 0
    for tenant, row_id in (("t1", a), ("t2", b.action_id), ("t1", c.action_id)):
        assert (await ledger.get(live, tenant, row_id))["state"] == "expired"
    assert await live.agent_instructions.count_documents({}) == 0


async def test_expiry_runs_during_a_stop_and_an_expired_card_never_dispatches_after_resume(live):
    """D-13 / PROH-81-08."""
    action_id = await _card(live)
    await live.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"stop": {"active": True}}})
    later = datetime.now(timezone.utc) + APPROVAL_TTL + timedelta(minutes=1)
    assert (await approvals.approve(live, "t1", action_id, approver=APPROVER, now=later))["status"] == "stopped"
    assert (await ledger.get(live, "t1", action_id))["state"] == "awaiting_approval"
    assert await approvals.expire_due(live, now=later) == 1
    await live.autonomy_settings.update_one({"tenantId": "t1"}, {"$set": {"stop": None}})
    assert (await approvals.approve(live, "t1", action_id, approver=APPROVER, now=later))["status"] == "already_handled"
    assert (await ledger.get(live, "t1", action_id))["state"] == "expired"
    assert await live.agent_instructions.count_documents({}) == 0


async def _executed_block(db, ip=IP, key=None, tenant="t1", target="a1"):
    d = await gate.decide(db, _req(tenant=tenant, action="block_ip", ip=ip, target=target, key=key or f"b|{ip}"),
                          master_shadow=False)
    assert d.state == "dispatching", d
    out = await gate.execute(db, tenant, d.action_id, command="block_ip", agent_id=target,
                             params={"ip_address": ip})
    assert out["status"] == "queued"
    row = await ledger.transition(db, tenant, d.action_id, ("dispatching",), "executed")
    assert row
    return d.action_id


async def test_undo_writes_one_undo_instruction_and_marks_the_row_undone(live):
    action_id = await _executed_block(live)
    out = await approvals.undo(live, "t1", action_id, actor=APPROVER)
    assert out["status"] == "undone"
    row = await ledger.get(live, "t1", action_id)
    assert row["state"] == "undone" and row["undo"]["action"] == "unblock_ip"
    assert row["undo"]["params"] == {"ip_address": IP} and row["undo"]["undoneAt"] is not None
    assert row["undo"]["undoneBy"] == APPROVER and len(row["instructionIds"]) == 2
    undo = await live.agent_instructions.find_one({"type": "unblock_ip"})
    assert undo["autonomy"] == {"actionId": action_id, "tenantId": "t1", "kind": "undo"}
    assert undo["payload"] == {"ip_address": IP} and undo["agent_id"] == "a1"
    assert await live.agent_instructions.count_documents({}) == 2
    assert (await approvals.undo(live, "t1", action_id, actor=APPROVER))["status"] == "already_handled"
    assert await live.agent_instructions.count_documents({}) == 2


async def test_undo_still_works_during_a_stop(live):
    action_id = await _executed_block(live)
    await seed_platform_stop(live)
    assert (await approvals.undo(live, "t1", action_id, actor=APPROVER))["status"] == "undone"
    assert await live.agent_instructions.count_documents({"type": "unblock_ip"}) == 1


async def test_undo_of_a_row_without_an_undo_and_of_other_states(live):
    d = await gate.decide(live, _req(action="restart_service", key="rs"), master_shadow=False)
    out = await gate.execute(live, "t1", d.action_id, command="restart_service", agent_id="a1", params={})
    assert out["status"] == "queued", out      # the decided step (81-15 binding)
    await ledger.transition(live, "t1", d.action_id, ("dispatching",), "executed")
    assert (await approvals.undo(live, "t1", d.action_id, actor=APPROVER))["status"] == "no_undo"
    suggested = await gate.suggest(live, _req(action="block_ip", ip="203.0.113.50", key="sg"), master_shadow=False)
    assert (await approvals.undo(live, "t1", suggested.action_id, actor=APPROVER))["status"] == "refused"
    assert (await approvals.undo(live, "t1", "AO-none", actor=APPROVER))["status"] == "not_found"
    assert (await approvals.undo(live, "t2", d.action_id, actor=APPROVER))["status"] == "not_found"


async def test_undo_runs_the_breaker_afterwards(live):
    action_id = await _executed_block(live)
    with patch("autonomous_ops.breaker.evaluate", AsyncMock(return_value=True)) as ev:
        out = await approvals.undo(live, "t1", action_id, actor=APPROVER)
    ev.assert_awaited_once()
    assert ev.await_args.args[1] == "t1" and out["status"] == "undone"


async def test_undo_whose_instruction_cannot_be_written_puts_the_row_back(live):
    action_id = await _executed_block(live)
    with patch.object(gate, "execute", AsyncMock(return_value={"status": "refused", "reason": "dispatch_failed"})):
        out = await approvals.undo(live, "t1", action_id, actor=APPROVER)
    assert out == {"status": "refused", "reason": "dispatch_failed"}
    row = await ledger.get(live, "t1", action_id)
    assert row["state"] == "executed" and row["undo"]["undoneAt"] is None
