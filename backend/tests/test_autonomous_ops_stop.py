"""Autonomous Ops stop switch and delivery hold-back (Phase 81, plan 81-05, GATE-06 / D-11 to D-15).
Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py.

Value: protects=a stop takes effect on the next agent poll with no restart, at every queue an agent
reads, and nothing it holds back is ever delivered after the stop is cleared; fails_when=a stamped
action reaches an agent during a stop, an unstamped instruction is touched, a read failure delivers
instead of withholding, or the wrong person can clear a stop;
no_claim=the HTTP routes (plan 81-09) and a real agent poll on the live server.
"""
import os
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agent_instruction_endpoints
import agent_tasks_endpoints
import deployment_result_endpoints
from autonomous_ops import delivery, gate, ledger, protected, settings, stop
from response_orchestrator import ResponseOrchestrator
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_agent, seed_platform_stop, seed_tenant

IP = "203.0.113.7"
TENANT_ACTOR = {"username": "alice", "display": "Alice", "tier": "tenant"}
PLATFORM_ACTOR = {"username": "root", "display": "Root", "tier": "platform"}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv("AUTONOMOUS_REMEDIATION_DRY_RUN", raising=False)
    protected.cache_clear()


async def _seed(db, tenant="t1", agent="a1"):
    await seed_tenant(db, tenant, shadow=False)
    await db.tenants.update_one({"id": tenant}, {"$set": {"agentCapabilities": ["all"]}})
    await seed_agent(db, tenant, agent)


@pytest.fixture
async def live(mongo_db):
    await ledger.ensure_indexes(mongo_db)
    await _seed(mongo_db)
    return mongo_db


def _req(tenant="t1", action="block_ip", target="a1", ip=IP, key=None):
    return gate.ActionRequest(tenant_id=tenant, kind="security", origin="test", actions=[action], targets=[target],
                              params={"ip_address": ip}, dedupe_key=key or f"{tenant}|{action}|{target}|{ip}",
                              reason={"ruleId": "test", "inputs": {}}, dispatcher="instruction")


async def _queue_action(db, tenant="t1", agent="a1", ip=IP, command="block_ip"):
    """Decide an allow_auto action and write its stamped instruction. Returns (action_id, task_id)."""
    d = await gate.decide(db, _req(tenant=tenant, action=command, target=agent, ip=ip), master_shadow=False)
    assert d.outcome == "allow_auto" and d.state == "dispatching", d
    out = await gate.execute(db, tenant, d.action_id, command=command, agent_id=agent, params={"ip_address": ip})
    assert out["status"] == "queued", out
    return d.action_id, out["task_id"]


async def _human_instruction(db, tenant="t1", agent="a1", task_id="human-1"):
    await db.agent_instructions.insert_one({
        "id": task_id, "agent_id": agent, "tenantId": tenant, "type": "custom_task", "status": "pending",
        "payload": {"x": 1}, "created_at": datetime.now(timezone.utc).isoformat()})


def _request():
    req = MagicMock()
    req.headers = {"host": "10.0.0.1"}
    req.url.scheme = "http"
    return req


async def _poll_tasks(db, tenant="t1", agent="a1"):
    with patch.object(agent_tasks_endpoints, "get_database", return_value=db):
        return await agent_tasks_endpoints.get_agent_instructions(
            agent, request=_request(), _tenant={"tenant_id": tenant, "authenticated_agent_id": agent})


async def _poll_deployment(db, tenant="t1", agent="a1"):
    with patch.object(deployment_result_endpoints, "get_database", return_value=db):
        return await deployment_result_endpoints.get_agent_instructions(
            agent, request=_request(), caller={"tenant_id": tenant, "sub": agent})


async def _poll_unmounted(db, tenant="t1", agent="a1"):
    user = MagicMock(role="admin", tenant_id=tenant, tenantId=tenant)
    with patch.object(agent_instruction_endpoints, "get_database", return_value=db):
        return await agent_instruction_endpoints.get_agent_instructions(agent, current_user=user)


async def _instr(db, task_id):
    return await db.agent_instructions.find_one({"id": task_id}, {"_id": 0})


async def _control_rows(db, event):
    return await db.autonomy_actions.find({"kind": "control", "controlEvent": event}, {"_id": 0}).to_list(10)


# ---------------------------------------------------------------- Task 1: the tracer

async def test_tracer_tenant_stop_holds_back_the_queued_instruction_at_the_next_poll(live):
    action_id, task_id = await _queue_action(live)
    await _human_instruction(live)

    with patch("autonomous_ops.stop.notify.notify", new=AsyncMock()) as notice:
        out = await stop.press(live, scope="tenant", tenant_id="t1", actor=TENANT_ACTOR, reason=None)

    assert out["status"] == "stopped" and out["stop"]["active"] is True
    assert out["stop"]["pressedBy"]["username"] == "alice" and out["stop"]["pressedByTier"] == "tenant"
    assert out["cancelled"] == 1
    notice.assert_awaited_once()
    controls = await _control_rows(live, "stop_pressed")
    assert len(controls) == 1 and controls[0]["tenantId"] == "t1" and controls[0]["actor"]["username"] == "alice"
    events = [e["action"] async for e in live.audit_logs.find({"tenantId": "t1"})]
    assert "autonomous_ops.stop_pressed" in events

    delivered = await _poll_tasks(live)

    assert [d["task_id"] for d in delivered] == ["human-1"]           # unstamped work still flows
    assert (await _instr(live, task_id))["status"] == "cancelled_by_stop"
    assert (await ledger.get(live, "t1", action_id))["state"] == "cancelled_by_stop"
    assert (await _instr(live, "human-1"))["status"] == "sent"

    # Clearing the stop does not bring the held-back instruction back.
    cleared = await stop.clear(live, scope="tenant", tenant_id="t1", actor=TENANT_ACTOR, reason="all clear",
                               actor_is_super_admin=False, actor_has_manage=True)
    assert cleared["status"] == "cleared"
    d2 = await gate.decide(live, _req(ip="203.0.113.9"), master_shadow=False)
    assert d2.reason != "tenant_stop" and d2.outcome == "allow_auto"
    assert await _poll_tasks(live) == []
    assert (await _instr(live, task_id))["status"] == "cancelled_by_stop"
    assert (await ledger.get(live, "t1", action_id))["state"] == "cancelled_by_stop"


# ---------------------------------------------------------------- Task 2: every other delivery path

POLLS = {"deployment_result": _poll_deployment, "instruction_endpoints": _poll_unmounted}


async def _stop_without_cancelling(db, tenant="t1"):
    """A tenant stop written straight into the settings, so the press-time bulk cancel does not
    run: this is the state of a stop pressed while a poll was already about to deliver."""
    await settings.update(db, tenant, {"stop": {"active": True, "scope": "tenant", "pressedByTier": "tenant",
                                                "pressedBy": {"username": "alice", "display": "Alice"},
                                                "pressedAt": datetime.now(timezone.utc), "reason": None}},
                          actor="test")


@pytest.mark.parametrize("poll", POLLS.values(), ids=POLLS.keys())
async def test_stamped_is_held_back_and_unstamped_delivered_by_the_other_handlers(live, poll):
    action_id, task_id = await _queue_action(live)
    await _human_instruction(live)
    await _stop_without_cancelling(live)

    delivered = await poll(live)

    assert [d["type"] for d in delivered] == ["custom_task"]
    assert (await _instr(live, task_id))["status"] == "cancelled_by_stop"
    assert (await ledger.get(live, "t1", action_id))["state"] == "cancelled_by_stop"


@pytest.mark.parametrize("poll", POLLS.values(), ids=POLLS.keys())
async def test_a_stamped_instruction_is_delivered_when_no_stop_is_on(live, poll):
    # control: the hold-back is a stop effect, not a blanket block on stamped work
    action_id, task_id = await _queue_action(live)

    delivered = await poll(live)

    assert [d["type"] for d in delivered] == ["block_ip"]
    assert (await ledger.get(live, "t1", action_id))["state"] == "dispatching"


async def _queue_exempt(db, tenant="t1", agent="a1"):
    """One undo (row undone) and one compensate (row failed) stamped instruction."""
    ids = {}
    for kind, state, command in (("undo", "undone", "unblock_ip"), ("compensate", "failed", "unblock_ip")):
        row = await ledger.create_intent(db, {"tenantId": tenant, "kind": "security", "state": state,
                                              "command": command, "actions": [command], "targets": [agent]})
        out = await gate.execute(db, tenant, row["id"], command=command, agent_id=agent,
                                 params={"ip_address": IP}, kind=kind)
        assert out["status"] == "queued", out
        ids[kind] = out["task_id"]
    return ids


async def test_platform_stop_holds_every_tenant_but_undo_and_compensate_flow(live):
    await _seed(live, "t2", "a2")
    _, t1_task = await _queue_action(live, "t1", "a1")
    _, t2_task = await _queue_action(live, "t2", "a2", ip="203.0.113.8")
    exempt = await _queue_exempt(live)
    await seed_platform_stop(live)

    delivered = await _poll_tasks(live)
    other = await _poll_tasks(live, "t2", "a2")

    assert sorted(d["task_id"] for d in delivered) == sorted(exempt.values())
    assert other == []
    assert (await _instr(live, t1_task))["status"] == "cancelled_by_stop"
    assert (await _instr(live, t2_task))["status"] == "cancelled_by_stop"


async def test_response_tasks_are_held_back_under_a_stop_but_manual_ones_are_returned(live):
    d = await gate.decide(live, _req(), master_shadow=False)
    out = await gate.execute_response_task(live, "t1", d.action_id, action="block_ip", agent_id="a1",
                                           params={"ip_address": IP})
    assert out["status"] == "queued"
    await live.response_tasks.insert_one({"task_id": "RSP-manual", "agent_id": "a1", "tenantId": "t1",
                                          "action": "kill_process", "status": "queued", "params": {}})
    await seed_platform_stop(live)

    with patch("response_orchestrator.get_database", return_value=live):
        tasks = await ResponseOrchestrator().get_pending_tasks("a1", tenant_id="t1")

    assert [t["task_id"] for t in tasks] == ["RSP-manual"]
    held = await live.response_tasks.find_one({"task_id": out["task_id"]})
    assert held["status"] == "cancelled_by_stop"
    assert (await ledger.get(live, "t1", d.action_id))["state"] == "cancelled_by_stop"


async def test_a_stop_that_cannot_be_read_withholds_stamped_and_delivers_unstamped(live):
    action_id, task_id = await _queue_action(live)
    await _human_instruction(live)

    with patch.object(settings, "platform_stop", AsyncMock(side_effect=RuntimeError("db down"))):
        delivered = await _poll_tasks(live)

    assert [d["task_id"] for d in delivered] == ["human-1"]
    assert (await _instr(live, task_id))["status"] == "pending"          # left as it was
    assert (await ledger.get(live, "t1", action_id))["state"] == "dispatching"
    # The next poll with a readable stop delivers it (nothing was cancelled by the read failure).
    assert [d["task_id"] for d in await _poll_tasks(live)] == [task_id]


async def test_an_unreadable_ledger_withholds_the_stamped_instruction(live):
    _, task_id = await _queue_action(live)
    with patch.object(delivery, "_row", AsyncMock(side_effect=delivery._Unreadable())):
        assert await _poll_tasks(live) == []
    assert (await _instr(live, task_id))["status"] == "pending"


async def test_no_stamped_instruction_means_no_database_call():
    db = MagicMock()
    items = [{"_id": 1, "type": "custom_task"}, {"_id": 2, "type": "x", "autonomy": {}}]
    assert await delivery.hold_back_autonomous(db, "t1", items) is items
    assert await delivery.hold_back_response_tasks(db, "t1", [{"task_id": "r"}]) == [{"task_id": "r"}]
    assert db.mock_calls == []


async def test_a_row_of_another_tenant_is_withheld_and_refused(live):
    await _seed(live, "t2", "a2")
    action_id, _ = await _queue_action(live, "t2", "a2", ip="203.0.113.8")        # t2's row
    await live.agent_instructions.insert_one({
        "id": "forged", "agent_id": "a1", "tenantId": "t1", "type": "block_ip", "status": "pending",
        "payload": {}, "triggered_by": "autonomous_ops",
        "autonomy": {"actionId": action_id, "tenantId": "t1", "kind": "action"}})

    assert await _poll_tasks(live) == []

    assert (await _instr(live, "forged"))["status"] == "refused"
    assert (await ledger.get(live, "t2", action_id))["state"] == "dispatching"     # t2's row untouched


async def test_missing_and_non_dispatchable_rows_are_refused(live):
    await live.agent_instructions.insert_many([
        {"id": "ghost", "agent_id": "a1", "tenantId": "t1", "type": "block_ip", "status": "pending", "payload": {},
         "autonomy": {"actionId": "AO-nope", "tenantId": "t1", "kind": "action"}},
        {"id": "done", "agent_id": "a1", "tenantId": "t1", "type": "block_ip", "status": "pending", "payload": {},
         "autonomy": {"actionId": "AO-done", "tenantId": "t1", "kind": "action"}}])
    await ledger.create_intent(live, {"id": "AO-done", "tenantId": "t1", "kind": "security", "state": "executed",
                                      "command": "block_ip"})

    assert await _poll_tasks(live) == []

    assert (await _instr(live, "ghost"))["status"] == "refused"
    assert (await _instr(live, "done"))["status"] == "refused"


async def test_press_bulk_cancels_for_its_scope_and_returns_the_count(live):
    await _seed(live, "t2", "a2")
    _, a1_task = await _queue_action(live, "t1", "a1")
    _, a2_task = await _queue_action(live, "t2", "a2", ip="203.0.113.8")
    exempt = await _queue_exempt(live)
    d = await gate.decide(live, _req(ip="203.0.113.9"), master_shadow=False)
    await gate.execute_response_task(live, "t1", d.action_id, action="block_ip", agent_id="a1", params={})

    tenant = await stop.press(live, scope="tenant", tenant_id="t1", actor=TENANT_ACTOR)

    assert tenant["cancelled"] == 2                                  # one instruction + one response task
    assert (await _instr(live, a1_task))["status"] == "cancelled_by_stop"
    assert (await _instr(live, a2_task))["status"] == "pending"      # other tenant untouched
    assert [(await _instr(live, t))["status"] for t in exempt.values()] == ["pending", "pending"]

    platform = await stop.press(live, scope="platform", tenant_id=None, actor=PLATFORM_ACTOR, reason="drill")
    assert platform["status"] == "stopped" and platform["cancelled"] == 1
    assert (await _instr(live, a2_task))["status"] == "cancelled_by_stop"
    assert [(await _instr(live, t))["status"] for t in exempt.values()] == ["pending", "pending"]
    assert len(await _control_rows(live, "platform_stop_pressed")) == 1


# ---------------------------------------------------------------- Task 3: authority, reasons, capability map

def _stop(scope="tenant", tier="tenant"):
    return {"active": True, "scope": scope, "pressedByTier": tier, "pressedBy": {"username": "x", "display": "X"},
            "pressedAt": datetime.now(timezone.utc), "reason": None}


@pytest.mark.parametrize("stop_doc, super_admin, manage, expected", [
    (_stop("tenant", "tenant"), False, True, True),          # tenant stop, tenant tier, manage holder
    (_stop("tenant", "tenant"), True, False, True),          # tenant stop, tenant tier, Super Admin
    (_stop("tenant", "tenant"), False, False, False),        # approver without manage
    (_stop("tenant", "platform"), False, True, False),       # tenant stop pressed by a Super Admin, manage holder
    (_stop("tenant", "platform"), True, False, True),        # ... the Super Admin
    (_stop("platform", "platform"), False, True, False),     # platform stop, manage holder
    (_stop("platform", "platform"), True, False, True),      # platform stop, Super Admin
], ids=["tenant-manage", "tenant-superadmin", "tenant-approver-only", "platform-tier-manage",
        "platform-tier-superadmin", "platform-manage", "platform-superadmin"])
def test_can_clear_matrix(stop_doc, super_admin, manage, expected):
    assert stop.can_clear(stop_doc, actor_is_super_admin=super_admin, actor_has_manage=manage) is expected


def test_can_clear_fails_closed_on_unknown_origin():
    assert stop.can_clear({"active": True, "scope": "tenant"}, actor_is_super_admin=False, actor_has_manage=True) is False
    assert stop.can_clear(None, actor_is_super_admin=True, actor_has_manage=True) is False


async def _clear(db, reason, scope="tenant", tenant="t1", **kw):
    args = dict(actor_is_super_admin=False, actor_has_manage=True)
    args.update(kw)
    return await stop.clear(db, scope=scope, tenant_id=tenant if scope == "tenant" else None,
                            actor=TENANT_ACTOR, reason=reason, **args)


@pytest.mark.parametrize("reason", [None, "", "   \n\t ", "x" * 501], ids=["none", "empty", "blank", "501-chars"])
async def test_clear_needs_a_real_reason_and_leaves_the_stop_on(live, reason):
    await stop.press(live, scope="tenant", tenant_id="t1", actor=TENANT_ACTOR)

    out = await _clear(live, reason)

    assert out["status"] == "invalid_reason"
    assert (await settings.load(live, "t1")).stop["active"] is True
    assert await _control_rows(live, "stop_cleared") == []


async def test_clear_with_a_reason_records_it_and_keeps_the_press_fields(live):
    pressed = await stop.press(live, scope="tenant", tenant_id="t1", actor=TENANT_ACTOR, reason="  suspicious  ")
    assert pressed["stop"]["reason"] == "suspicious"

    out = await _clear(live, "  false alarm  ")

    assert out["status"] == "cleared"
    stored = (await settings.load(live, "t1")).stop
    assert stored["active"] is False and stored["clearReason"] == "false alarm"
    assert stored["clearedBy"]["username"] == "alice" and stored["pressedBy"]["username"] == "alice"
    assert stored["reason"] == "suspicious" and stored["clearedAt"]
    rows = await _control_rows(live, "stop_cleared")
    assert len(rows) == 1 and rows[0]["reasonText"] == "false alarm"
    assert "autonomous_ops.stop_cleared" in [e["action"] async for e in live.audit_logs.find({"tenantId": "t1"})]


async def test_clear_checks_the_stored_origin_of_the_stop(live):
    await stop.press(live, scope="tenant", tenant_id="t1", actor=PLATFORM_ACTOR)       # pressed at platform tier
    assert (await _clear(live, "ok"))["status"] == "forbidden"
    assert (await settings.load(live, "t1")).stop["active"] is True
    assert (await _clear(live, "ok", actor_is_super_admin=True, actor_has_manage=False))["status"] == "cleared"

    await stop.press(live, scope="platform", tenant_id=None, actor=PLATFORM_ACTOR)
    assert (await _clear(live, "ok", scope="platform"))["status"] == "forbidden"
    assert settings.stop_active(await settings.platform_stop(live))
    out = await _clear(live, "all clear", scope="platform", actor_is_super_admin=True, actor_has_manage=False)
    assert out["status"] == "cleared" and not settings.stop_active(await settings.platform_stop(live))
    assert len(await _control_rows(live, "platform_stop_cleared")) == 1


async def test_clear_when_not_stopped_and_press_when_stopped(live):
    assert (await _clear(live, "ok"))["status"] == "not_stopped"
    assert (await _clear(live, "ok", scope="platform", actor_is_super_admin=True))["status"] == "not_stopped"

    first = await stop.press(live, scope="tenant", tenant_id="t1", actor=TENANT_ACTOR)
    second = await stop.press(live, scope="tenant", tenant_id="t1", actor=PLATFORM_ACTOR, reason="again")

    assert first["status"] == "stopped" and second["status"] == "already_stopped"
    assert second["stop"]["pressedBy"]["username"] == "alice" and second["cancelled"] == 0
    assert len(await _control_rows(live, "stop_pressed")) == 1


async def test_press_reason_is_optional_but_capped(live):
    too_long = await stop.press(live, scope="tenant", tenant_id="t1", actor=TENANT_ACTOR, reason="x" * 501)
    assert too_long["status"] == "invalid_reason" and not settings.stop_active((await settings.load(live, "t1")).stop)
    exact = await stop.press(live, scope="tenant", tenant_id="t1", actor=TENANT_ACTOR, reason="x" * 500)
    assert exact["status"] == "stopped"


async def test_press_notifies_once_for_each_scope(live):
    with patch("autonomous_ops.stop.notify.notify", new=AsyncMock()) as notice:
        await stop.press(live, scope="tenant", tenant_id="t1", actor=TENANT_ACTOR)
        await stop.press(live, scope="tenant", tenant_id="t1", actor=TENANT_ACTOR)      # already stopped: no notice
        await stop.press(live, scope="platform", tenant_id=None, actor=PLATFORM_ACTOR, reason="drill")
    assert notice.await_count == 2
    assert notice.await_args_list[1].args[1] == "platform-admin"
    assert "drill" in notice.await_args_list[1].kwargs["message"]


async def test_nothing_but_clear_turns_an_active_stop_off(live):
    from autonomous_ops import reconciler
    await stop.press(live, scope="tenant", tenant_id="t1", actor=TENANT_ACTOR)
    await stop.press(live, scope="platform", tenant_id=None, actor=PLATFORM_ACTOR)

    await settings.ensure_tenant(live, "t1")
    await settings.ensure_all_tenants(live)
    await settings.set_level(live, "t1", "suggest", actor="x")
    await settings.set_max_level(live, "t1", "undoable_auto", actor="x")
    await settings.set_shadow(live, "t1", True, actor="x")
    await reconciler.tick(live)

    assert settings.stop_active((await settings.load(live, "t1")).stop)
    assert settings.stop_active(await settings.platform_stop(live))
    # A platform clear does not touch the tenant's own stop, and vice versa.
    await _clear(live, "ok", scope="platform", actor_is_super_admin=True)
    assert settings.stop_active((await settings.load(live, "t1")).stop)


def test_every_registry_command_maps_to_a_capability():
    import agent_capabilities
    from autonomous_ops import registry
    missing = [n for n in sorted(registry.commands()) if agent_capabilities.instruction_capability({"type": n}) is None]
    assert missing == []
    want = {"restart_service": "remediation_executor", "quarantine_file": "remediation_executor",
            "unquarantine_file": "remediation_executor", "restore_host": "remediation_executor",
            "reboot_host": "patch_installer", "rollback_ransomware": "vss_manager",
            "autonomous_remediation": "autonomous_response"}
    for name, cap in want.items():
        assert agent_capabilities.instruction_capability({"type": name}) == cap, name
