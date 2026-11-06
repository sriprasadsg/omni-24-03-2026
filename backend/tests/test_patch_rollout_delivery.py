"""Staged patch rollouts, plan 84-04, task 1: an instruction whose window closed is never delivered (PTCH-07, D-04).
Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py.

Value: protects=PTCH-07 / T-84-12 / D-15: an install or restart that waited in the queue past the window it was
issued for is dropped at the agent poll (refused, instruction_expired) on every poll path, one still inside its
window is delivered as before, an undo is delivered whatever its clock, and a plain batch costs no database call;
fails_when=an expired instruction reaches an agent after the host comes back online, an unexpired one is held
back, an undo is held back by the clock, or a batch with no expiry touches the database;
no_claim=a real agent poll on the live server.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agent_instruction_endpoints
import agent_tasks_endpoints
import deployment_result_endpoints
from autonomous_ops import delivery, gate, ledger, protected
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_agent, seed_platform_stop, seed_tenant

IP = "203.0.113.7"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv("AUTONOMOUS_REMEDIATION_DRY_RUN", raising=False)
    protected.cache_clear()


@pytest.fixture
async def live(mongo_db):
    await ledger.ensure_indexes(mongo_db)
    await seed_tenant(mongo_db, "t1", shadow=False)
    await mongo_db.tenants.update_one({"id": "t1"}, {"$set": {"agentCapabilities": ["all"]}})
    await seed_agent(mongo_db, "t1", "a1")
    return mongo_db


async def queue(db, expires_at, *, ip=IP):
    """A stamped instruction for an automatic row, written with ``expires_at``. Returns (action id, task id)."""
    d = await gate.decide(db, gate.ActionRequest(
        tenant_id="t1", kind="security", origin="test", actions=["block_ip"], targets=["a1"],
        params={"ip_address": ip}, dedupe_key=f"t1|block_ip|a1|{ip}", reason={"ruleId": "test", "inputs": {}},
        dispatcher="instruction"), master_shadow=False)
    assert d.state == "dispatching", d
    out = await gate.execute(db, "t1", d.action_id, command="block_ip", agent_id="a1",
                             params={"ip_address": ip}, expires_at=expires_at)
    assert out["status"] == "queued", out
    return d.action_id, out["task_id"]


def utc(**delta):
    return datetime.now(timezone.utc) + timedelta(**delta)


def _request():
    req = MagicMock()
    req.headers = {"host": "10.0.0.1"}
    req.url.scheme = "http"
    return req


async def poll_tasks(db):
    with patch.object(agent_tasks_endpoints, "get_database", return_value=db):
        return await agent_tasks_endpoints.get_agent_instructions(
            "a1", request=_request(), _tenant={"tenant_id": "t1", "authenticated_agent_id": "a1"})


async def poll_deployment(db):
    with patch.object(deployment_result_endpoints, "get_database", return_value=db):
        return await deployment_result_endpoints.get_agent_instructions(
            "a1", request=_request(), caller={"tenant_id": "t1", "sub": "a1"})


async def poll_unmounted(db):
    user = MagicMock(role="admin", tenant_id="t1", tenantId="t1")
    with patch.object(agent_instruction_endpoints, "get_database", return_value=db):
        return await agent_instruction_endpoints.get_agent_instructions("a1", current_user=user)


POLLS = (poll_tasks, poll_deployment, poll_unmounted)


async def ids(db, delivered):
    """The task ids of a poll response. The deployment poll names an instruction by its Mongo _id, the others by
    its task id, so both are mapped back to the task id."""
    by_oid = {str(d["_id"]): d["id"] async for d in db.agent_instructions.find({}, {"_id": 1, "id": 1})}
    return [by_oid.get(d.get("id")) or d.get("task_id") or d.get("id") for d in delivered]


async def doc(db, task_id):
    return await db.agent_instructions.find_one({"id": task_id}, {"_id": 0})


# ---------------------------------------------------------------- the rule

async def test_an_instruction_past_its_expiry_is_refused_and_not_delivered(live):
    """fails_when=a host that comes back online after the window closed still runs the install."""
    _, task_id = await queue(live, utc(seconds=-1))
    assert await delivery.hold_back_autonomous(live, "t1", [await live.agent_instructions.find_one({"id": task_id})]) == []
    held = await doc(live, task_id)
    assert held["status"] == "refused" and held["error"] == "instruction_expired" and held["refused_at"]


async def test_an_instruction_inside_its_window_is_delivered(live):
    _, task_id = await queue(live, utc(minutes=1))
    item = await live.agent_instructions.find_one({"id": task_id})
    assert await delivery.hold_back_autonomous(live, "t1", [item]) == [item]
    assert (await doc(live, task_id))["status"] == "pending"


async def test_a_naive_expiry_is_read_as_utc(live):
    """Mongo hands back naive datetimes: one a second in the past must still expire, one ahead must not."""
    _, past = await queue(live, utc(seconds=-1), ip="203.0.113.8")
    _, ahead = await queue(live, utc(minutes=5), ip="203.0.113.9")
    items = [await live.agent_instructions.find_one({"id": t}) for t in (past, ahead)]
    assert all(i["expiresAt"].tzinfo is None for i in items)           # the shape the poll really sees
    kept = await delivery.hold_back_autonomous(live, "t1", items)
    assert [k["id"] for k in kept] == [ahead]
    assert (await doc(live, past))["error"] == "instruction_expired"


async def test_an_expiry_exactly_now_counts_as_closed(live):
    _, task_id = await queue(live, utc())
    item = await live.agent_instructions.find_one({"id": task_id})
    item["expiresAt"] = datetime.now(timezone.utc) - timedelta(milliseconds=1)
    assert await delivery.hold_back_autonomous(live, "t1", [item]) == []


async def test_an_expiry_that_is_not_a_date_is_ignored(live):
    """A bad value is not a reason to drop work: only a real datetime in the past expires an item."""
    _, task_id = await queue(live, utc(minutes=5))
    item = await live.agent_instructions.find_one({"id": task_id})
    item["expiresAt"] = "yesterday"
    assert await delivery.hold_back_autonomous(live, "t1", [item]) == [item]


async def test_a_plain_batch_with_no_expiry_is_returned_unchanged_and_touches_no_database():
    """The existing hold-back contract: no stamped item, no gate-only item, no expiresAt -> identity, zero calls."""
    db = MagicMock()
    items = [{"_id": 1, "type": "custom_task"}, {"_id": 2, "type": "x", "autonomy": {}}]
    assert await delivery.hold_back_autonomous(db, "t1", items) is items
    assert db.mock_calls == []


async def test_an_unstamped_item_with_a_past_expiry_is_also_dropped(live):
    """The expiry is the item's own: a human-queued install carrying one is held to it too."""
    await live.agent_instructions.insert_one({
        "id": "man-1", "agent_id": "a1", "tenantId": "t1", "type": "install_patches", "status": "pending",
        "payload": {}, "expiresAt": utc(minutes=-5), "created_at": datetime.now(timezone.utc).isoformat()})
    item = await live.agent_instructions.find_one({"id": "man-1"})
    assert await delivery.hold_back_autonomous(live, "t1", [item]) == []
    assert (await doc(live, "man-1"))["error"] == "instruction_expired"


async def test_an_undo_is_delivered_during_a_stop_and_whatever_its_clock(live):
    """D-15: putting things back is never held by a stop or by a window. Undo carries no expiresAt; one that did
    would still be delivered."""
    row = await ledger.create_intent(live, {
        "tenantId": "t1", "kind": "security", "state": "undone", "command": "unblock_ip", "actions": ["block_ip"],
        "targets": ["a1"], "params": {"ip_address": IP},
        "steps": [{"command": "block_ip", "params": {"ip_address": IP}}],
        "rollback": [{"command": "unblock_ip", "params": {"ip_address": IP}}],
        "undo": {"available": True, "action": "unblock_ip", "params": {"ip_address": IP}}})
    out = await gate.execute(live, "t1", row["id"], command="unblock_ip", agent_id="a1",
                             params={"ip_address": IP}, kind="undo")
    assert out["status"] == "queued" and "expiresAt" not in await doc(live, out["task_id"])
    await seed_platform_stop(live)
    item = await live.agent_instructions.find_one({"id": out["task_id"]})
    assert await delivery.hold_back_autonomous(live, "t1", [item]) == [item]
    item["expiresAt"] = datetime.now(timezone.utc) - timedelta(hours=1)
    assert await delivery.hold_back_autonomous(live, "t1", [item]) == [item]
    assert (await doc(live, out["task_id"]))["status"] == "pending"


# ---------------------------------------------------------------- every poll path

@pytest.mark.parametrize("poll", POLLS, ids=lambda p: p.__name__)
async def test_an_expired_instruction_is_absent_from_every_poll_response(live, poll):
    _, expired = await queue(live, utc(seconds=-1), ip="203.0.113.10")
    _, current = await queue(live, utc(minutes=30), ip="203.0.113.11")
    delivered = await poll(live)
    assert await ids(live, delivered) == [current]
    assert (await doc(live, expired))["error"] == "instruction_expired"
    assert (await doc(live, expired))["status"] == "refused"
    assert expired not in await ids(live, await poll(live))             # the next poll does not bring it back


@pytest.mark.parametrize("poll", POLLS, ids=lambda p: p.__name__)
async def test_an_instruction_inside_its_window_is_delivered_by_every_poll(live, poll):
    _, task_id = await queue(live, utc(hours=2), ip="203.0.113.12")
    assert await ids(live, await poll(live)) == [task_id]
