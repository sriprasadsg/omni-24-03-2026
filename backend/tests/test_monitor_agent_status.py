"""Phase 81 plan 03 (GATE-12, D-24 (d)): monitor_agent_status marks agents Offline when
lastSeen is older than 5 minutes (polled every 30 s) and notifies exactly the agents that
this pass flipped.

The original GATE-12 premise (a 3600 s sleep) did not match the code; the loop already
slept 30 s. These tests pin the documented cadence and the wrong-agent notification fix.

Real Mongo (throwaway omni_test_* database) for the selection/update semantics; the cadence
test uses a fake db so it can count passes without touching a server.
"""
import ast
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests._mongo_test_db import mongo_db  # noqa: F401  (pytest fixture)

import app_background_tasks as abt

FROZEN_NOW = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return FROZEN_NOW.replace(tzinfo=None)
        return FROZEN_NOW.astimezone(tz)


def _seen(delta: timedelta) -> str:
    """lastSeen in the exact format the heartbeat writes (aware-UTC isoformat)."""
    return (FROZEN_NOW - delta).isoformat()


class _OneShotSleep:
    """asyncio.sleep stand-in that records its argument and cancels on the Nth call."""

    def __init__(self, cancel_on: int = 1):
        self.calls = []
        self.cancel_on = cancel_on

    async def __call__(self, seconds):
        self.calls.append(seconds)
        if len(self.calls) >= self.cancel_on:
            raise asyncio.CancelledError()


async def _seed(db):
    await db.agents.insert_many([
        {"id": "A", "tenantId": "t1", "hostname": "host-a", "status": "Online",
         "lastSeen": _seen(timedelta(minutes=6))},
        {"id": "B", "tenantId": "t1", "hostname": "host-b", "status": "Offline",
         "lastSeen": _seen(timedelta(days=3))},
        {"id": "C", "tenantId": "t2", "hostname": "host-c", "status": "Online",
         "lastSeen": _seen(timedelta(minutes=5))},
        {"id": "D", "tenantId": "t2", "hostname": "host-d", "status": "Online",
         "lastSeen": _seen(timedelta(seconds=10))},
    ])


async def _run_one_pass(db):
    """Run exactly one loop iteration against `db`; the first sleep cancels the loop."""
    ws = MagicMock()
    ws.broadcast_agent_status_change = AsyncMock()
    nm = MagicMock()
    nm.send_notification = AsyncMock()
    sleeper = _OneShotSleep(cancel_on=1)
    import websocket_manager
    import notification_manager as nm_mod
    with patch("database.get_database", return_value=db), \
         patch.object(abt, "datetime", _FrozenDatetime), \
         patch.object(websocket_manager, "broadcast_agent_status_change", ws.broadcast_agent_status_change), \
         patch.object(nm_mod, "notification_manager", nm), \
         patch.object(abt.asyncio, "sleep", sleeper):
        with pytest.raises(asyncio.CancelledError):
            await abt.monitor_agent_status()
    return ws.broadcast_agent_status_change, nm.send_notification, sleeper


async def test_only_the_agent_flipped_this_pass_is_broadcast_and_notified(mongo_db):
    await _seed(mongo_db)
    broadcast, notify, _ = await _run_one_pass(mongo_db)

    status = {a["id"]: a["status"] async for a in mongo_db.agents.find({}, {"id": 1, "status": 1})}
    assert status == {"A": "Offline", "B": "Offline", "C": "Online", "D": "Online"}

    # Compared as sets: exactly A, never the already-Offline stale QA agent B.
    assert {c.kwargs["agent_id"] for c in broadcast.await_args_list} == {"A"}
    assert broadcast.await_count == 1
    assert {c.args[1]["agent_id"] for c in notify.await_args_list} == {"A"}
    assert notify.await_count == 1
    event, payload, tenant = notify.await_args.args
    assert event == "agent.offline"
    assert payload["hostname"] == "host-a"
    assert tenant == "t1"


async def test_pass_with_no_stale_online_agents_does_nothing(mongo_db):
    await mongo_db.agents.insert_many([
        {"id": "B", "tenantId": "t1", "hostname": "host-b", "status": "Offline",
         "lastSeen": _seen(timedelta(days=3))},
        {"id": "D", "tenantId": "t2", "hostname": "host-d", "status": "Online",
         "lastSeen": _seen(timedelta(seconds=10))},
    ])
    broadcast, notify, _ = await _run_one_pass(mongo_db)
    assert broadcast.await_count == 0
    assert notify.await_count == 0
    status = {a["id"]: a["status"] async for a in mongo_db.agents.find({}, {"id": 1, "status": 1})}
    assert status == {"B": "Offline", "D": "Online"}


async def test_exact_threshold_stays_online_one_second_older_flips(mongo_db):
    await mongo_db.agents.insert_many([
        {"id": "EDGE", "tenantId": "t1", "hostname": "edge", "status": "Online",
         "lastSeen": _seen(timedelta(minutes=5))},
        {"id": "OVER", "tenantId": "t1", "hostname": "over", "status": "Online",
         "lastSeen": _seen(timedelta(minutes=5, seconds=1))},
    ])
    broadcast, notify, _ = await _run_one_pass(mongo_db)
    status = {a["id"]: a["status"] async for a in mongo_db.agents.find({}, {"id": 1, "status": 1})}
    assert status == {"EDGE": "Online", "OVER": "Offline"}
    assert {c.kwargs["agent_id"] for c in broadcast.await_args_list} == {"OVER"}
    assert {c.args[1]["agent_id"] for c in notify.await_args_list} == {"OVER"}


async def test_cadence_constants_and_every_iteration_runs_the_offline_pass():
    assert abt.AGENT_STATUS_POLL_SEC == 30
    assert abt.AGENT_OFFLINE_AFTER == timedelta(minutes=5)

    find_calls = []

    class _Cursor:
        async def to_list(self, length=None):
            return []

    class _Agents:
        def find(self, query, *a, **k):
            find_calls.append(query)
            return _Cursor()

        update_many = AsyncMock()

    fake_db = MagicMock()
    fake_db.agents = _Agents()

    sleeper = _OneShotSleep(cancel_on=4)
    with patch("database.get_database", return_value=fake_db), \
         patch.object(abt, "datetime", _FrozenDatetime), \
         patch.object(abt.asyncio, "sleep", sleeper):
        with pytest.raises(asyncio.CancelledError):
            await abt.monitor_agent_status()

    # Pass runs first (no leading sleep), then once per iteration.
    assert len(find_calls) == 4
    assert sleeper.calls == [abt.AGENT_STATUS_POLL_SEC] * 4
    assert all(s <= 300 for s in sleeper.calls)
    # Threshold is the frozen now minus 5 minutes, in the heartbeat's isoformat.
    expected = (FROZEN_NOW - timedelta(minutes=5)).isoformat()
    assert all(q == {"status": "Online", "lastSeen": {"$lt": expected}} for q in find_calls)
    fake_db.agents.update_many.assert_not_awaited()


async def test_tenant_context_is_reset_after_the_loop_exits(mongo_db):
    from tenant_context import get_tenant_id
    await _seed(mongo_db)
    await _run_one_pass(mongo_db)
    assert get_tenant_id() is None


_REMOVED_LOOP = "autonomous_remediation_loop"


def test_legacy_remediation_loop_is_not_scheduled():
    """GATE-05: nothing scheduled may reach the legacy run_cycle path."""
    assert not hasattr(abt, _REMOVED_LOOP)
    assert not hasattr(abt, "AutonomousRemediationService")

    backend_dir = os.path.join(os.path.dirname(__file__), "..")
    for fname in ("app_background_tasks.py", "app_startup.py"):
        with open(os.path.join(backend_dir, fname), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert all(a.name != _REMOVED_LOOP for a in node.names), fname
                assert all(a.name != "AutonomousRemediationService" for a in node.names), fname
            if isinstance(node, ast.Call):
                fn = node.func
                called = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
                if called == "create_task":
                    # No create_task argument, however nested, may call the removed loop.
                    for sub in ast.walk(node):
                        if isinstance(sub, ast.Call):
                            f = sub.func
                            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
                            assert name != _REMOVED_LOOP, fname
        assert _REMOVED_LOOP not in ast.dump(tree), fname
