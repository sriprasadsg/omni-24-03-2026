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
