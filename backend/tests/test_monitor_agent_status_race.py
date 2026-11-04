"""Phase 81 review WR-06: monitor_agent_status never marks an agent Offline whose heartbeat landed
between the read of the stale agents and the write, and it notifies only the agents it really flipped.

protects=GATE-12 (the Offline flag is what the gate's agent-support step and the approval re-check read);
fails_when=the update drops the ``lastSeen < threshold`` condition, so an agent that just checked in is
written Offline and a websocket event and an agent.offline notification are sent for it;
no_claim=the cadence and the plain selection rules (tests/test_monitor_agent_status.py).

Real Mongo (throwaway omni_test_* database); the heartbeat is a write made right after the monitor's read.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app_background_tasks as abt
from tests._mongo_test_db import mongo_db  # noqa: F401  (pytest fixture)

NOW = datetime(2026, 10, 26, 12, 0, 0, tzinfo=timezone.utc)


class _Frozen(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)


class _HeartbeatAfterRead:
    """The agents collection, except that right after the monitor's read returns, agent ``agent_id``
    checks in (its lastSeen becomes now), exactly as a heartbeat landing in that gap would."""

    def __init__(self, coll, agent_id):
        self._coll, self._agent_id = coll, agent_id

    def find(self, *args, **kwargs):
        cursor, coll, agent_id = self._coll.find(*args, **kwargs), self._coll, self._agent_id

        class _Cursor:
            async def to_list(self, length=None):
                docs = await cursor.to_list(length=length)
                await coll.update_one({"id": agent_id}, {"$set": {"lastSeen": NOW.isoformat()}})
                return docs
        return _Cursor()

    def __getattr__(self, name):
        return getattr(self._coll, name)


class _Db:
    def __init__(self, real, agents):
        self._real, self.agents = real, agents

    def __getattr__(self, name):
        return getattr(self._real, name)


async def _one_pass(db):
    broadcast, notify = AsyncMock(), MagicMock(send_notification=AsyncMock())

    async def stop(_seconds):
        raise asyncio.CancelledError()

    import notification_manager as nm_mod
    import websocket_manager
    with patch("database.get_database", return_value=db), patch.object(abt, "datetime", _Frozen), \
         patch.object(websocket_manager, "broadcast_agent_status_change", broadcast), \
         patch.object(nm_mod, "notification_manager", notify), patch.object(abt.asyncio, "sleep", stop):
        with pytest.raises(asyncio.CancelledError):
            await abt.monitor_agent_status()
    return broadcast, notify.send_notification


async def test_an_agent_that_checks_in_between_the_read_and_the_write_stays_online(mongo_db):  # noqa: F811
    old = (NOW - timedelta(minutes=9)).isoformat()
    await mongo_db.agents.insert_many([
        {"id": "A", "tenantId": "t1", "hostname": "host-a", "status": "Online", "lastSeen": old},
        {"id": "E", "tenantId": "t1", "hostname": "host-e", "status": "Online", "lastSeen": old},
    ])
    broadcast, notify = await _one_pass(_Db(mongo_db, _HeartbeatAfterRead(mongo_db.agents, "A")))

    status = {a["id"]: a["status"] async for a in mongo_db.agents.find({}, {"id": 1, "status": 1})}
    assert status == {"A": "Online", "E": "Offline"}
    assert [c.kwargs["agent_id"] for c in broadcast.await_args_list] == ["E"]
    assert [c.args[1]["agent_id"] for c in notify.await_args_list] == ["E"]


async def test_an_agent_another_pass_already_flipped_is_not_notified_twice(mongo_db):  # noqa: F811
    old = (NOW - timedelta(minutes=9)).isoformat()
    await mongo_db.agents.insert_one({"id": "A", "tenantId": "t1", "hostname": "host-a", "status": "Online",
                                      "lastSeen": old})

    class _FlippedByAnotherWorker(_HeartbeatAfterRead):
        def find(self, *args, **kwargs):
            cursor, coll = self._coll.find(*args, **kwargs), self._coll

            class _Cursor:
                async def to_list(self, length=None):
                    docs = await cursor.to_list(length=length)
                    await coll.update_one({"id": "A"}, {"$set": {"status": "Offline"}})
                    return docs
            return _Cursor()

    broadcast, notify = await _one_pass(_Db(mongo_db, _FlippedByAnotherWorker(mongo_db.agents, "A")))
    assert broadcast.await_count == 0 and notify.await_count == 0
