"""The dead-man switch (Phase 82, plan 82-08, HEAL-05, D-05, D-24): a sweep every 60 s finds the watchdog
silent and raises one in-app alarm per silence episode - never before the first heartbeat, never right after
a backend start, never through the on-call outbox.

Real Mongo through the throwaway database of tests/_mongo_test_db.py. Times are explicit: the sweep and the
heartbeat take a ``now``, and the backend start is the monkeypatched ``selfheal.PROCESS_STARTED_AT``.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-platform-health-deadman")

from autonomous_ops import PLATFORM_TENANT_ID, ledger, oncall, selfheal
from tests._autonomous_ops_http import api  # noqa: F401  (fixture)
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests._platform_health_world import STATUS, World, world  # noqa: F401  (fixtures)

TITLE = "The watchdog has gone silent"
ACTIONS = "/api/platform/autonomous-ops/actions?bucket=platform_health"


@pytest.fixture
def t0(monkeypatch):
    """The first heartbeat, an hour ago; the backend process has run for an hour by then."""
    start = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=1)
    monkeypatch.setattr(selfheal, "PROCESS_STARTED_AT", (start - timedelta(hours=1)).timestamp())
    return start


def at(t0, seconds):
    return t0 + timedelta(seconds=seconds)


async def _rows(db, kind):
    return [r async for r in db.autonomy_actions.find({"kind": "platform_health", "healthEvent": kind}, {"_id": 0})]


async def _notices(db):
    return [n async for n in db.notifications.find({"title": TITLE}, {"_id": 0})]


async def _beat(db, when):
    await selfheal.record_heartbeat(db, "omni", when)


async def _state(db):
    doc = await db.platform_health.find_one({"_id": "heartbeat"})
    return doc.get("alarmedAt")


@pytest.fixture
async def db(mongo_db):
    await ledger.ensure_indexes(mongo_db)
    await selfheal.ensure_indexes(mongo_db)
    await oncall.ensure_indexes(mongo_db)
    return mongo_db


async def test_one_alarm_per_silence_and_nothing_more_while_it_lasts(db, t0):
    await _beat(db, t0)
    assert (await selfheal.run_sweep_once(db, now=at(t0, 200)))["alarmed"] is False
    assert await _rows(db, "watchdog_silent") == [] and await _notices(db) == []
    assert (await selfheal.run_sweep_once(db, now=at(t0, 300)))["alarmed"] is False          # exactly 300 s is not silent

    result = await selfheal.run_sweep_once(db, now=at(t0, 301))
    assert result == {"state": "silent", "alarmed": True}
    rows, notices = await _rows(db, "watchdog_silent"), await _notices(db)
    assert len(rows) == 1 and len(notices) == 1
    assert rows[0]["tenantId"] == PLATFORM_TENANT_ID and rows[0]["healthParams"] == {"minutes": 5}
    assert rows[0]["healthChip"] == "critical" and rows[0]["host"] == "omni" and rows[0]["actor"] is None
    assert notices[0]["tenantId"] == PLATFORM_TENANT_ID and notices[0]["severity"] == "critical"
    assert notices[0]["message"].startswith(f"Last seen {t0:%H:%M} UTC.")
    assert await _state(db) is not None

    for seconds in (400, 900, 3000):
        assert (await selfheal.run_sweep_once(db, now=at(t0, seconds)))["alarmed"] is False
    assert len(await _rows(db, "watchdog_silent")) == 1 and len(await _notices(db)) == 1
    assert await db.notifications.count_documents({"tenantId": {"$ne": PLATFORM_TENANT_ID}}) == 0
    assert await db.oncall_outbox.count_documents({}) == 0                                     # never queued for on-call


async def test_the_next_heartbeat_clears_the_alarm_and_a_later_silence_is_a_new_episode(db, t0):
    await _beat(db, t0)
    await selfheal.run_sweep_once(db, now=at(t0, 301))
    await _beat(db, at(t0, 1000))
    assert await _state(db) is None
    assert len(await _rows(db, "watchdog_back")) == 1
    await _beat(db, at(t0, 1010))                                                              # a normal heartbeat adds nothing
    assert len(await _rows(db, "watchdog_back")) == 1
    assert (await selfheal.run_sweep_once(db, now=at(t0, 1100)))["alarmed"] is False

    assert (await selfheal.run_sweep_once(db, now=at(t0, 1400)))["alarmed"] is True
    assert len(await _rows(db, "watchdog_silent")) == 2 and len(await _notices(db)) == 2
    assert await db.oncall_outbox.count_documents({}) == 0


async def test_no_heartbeat_ever_never_alarms(db, t0):
    for seconds in (0, 301, 3600, 86400):
        assert await selfheal.run_sweep_once(db, now=at(t0, seconds)) == {"state": "not_installed", "alarmed": False}
    assert await _rows(db, "watchdog_silent") == [] and await _notices(db) == []
    assert await db.platform_health.count_documents({}) == 0                                   # the sweep creates nothing


async def test_a_backend_that_just_started_gives_the_watchdog_time(db, t0, monkeypatch):
    await _beat(db, t0)
    monkeypatch.setattr(selfheal, "PROCESS_STARTED_AT", at(t0, 400 - 60).timestamp())
    assert (await selfheal.run_sweep_once(db, now=at(t0, 400)))["alarmed"] is False             # up 60 s: grace
    assert (await selfheal.run_sweep_once(db, now=at(t0, 400 + 120)))["alarmed"] is False       # up 180 s: still grace
    assert (await selfheal.run_sweep_once(db, now=at(t0, 400 + 121)))["alarmed"] is True
    assert len(await _rows(db, "watchdog_silent")) == 1


async def test_two_sweeps_at_once_one_takes_the_lock_and_one_row_is_written(db, t0, monkeypatch):
    await _beat(db, t0)
    calls = []
    real = selfheal.silence_sweep

    async def slow(database, now):
        calls.append(1)
        await asyncio.sleep(0.3)
        return await real(database, now)
    monkeypatch.setattr(selfheal, "silence_sweep", slow)
    first, second = await asyncio.gather(selfheal.run_sweep_once(db, now=at(t0, 400)),
                                         selfheal.run_sweep_once(db, now=at(t0, 400)))
    assert sorted([first is None, second is None]) == [False, True] and len(calls) == 1
    assert len(await _rows(db, "watchdog_silent")) == 1 and len(await _notices(db)) == 1
    assert selfheal.LOCK_NAME == "autonomous_ops_selfheal" and selfheal.SWEEP_EVERY == 60


async def test_two_sweeps_without_a_lock_still_alarm_once(db, t0):
    await _beat(db, t0)
    results = await asyncio.gather(selfheal.silence_sweep(db, at(t0, 400)), selfheal.silence_sweep(db, at(t0, 400)))
    assert sorted(r["alarmed"] for r in results) == [False, True]
    assert len(await _rows(db, "watchdog_silent")) == 1 and len(await _notices(db)) == 1


async def test_a_heartbeat_that_arrives_during_the_sweep_wins(db, t0, monkeypatch):
    await _beat(db, t0)
    stale = await selfheal.get_heartbeat(db)

    async def old_read(_db):
        return stale
    monkeypatch.setattr(selfheal, "get_heartbeat", old_read)
    await _beat(db, at(t0, 395))                                                               # lands after the sweep read
    assert (await selfheal.silence_sweep(db, at(t0, 400)))["alarmed"] is False
    assert await _rows(db, "watchdog_silent") == [] and await _state(db) is None


async def test_a_failed_alarm_is_tried_again_by_the_next_sweep(db, t0, monkeypatch):
    await _beat(db, t0)
    real = ledger.record_platform_health
    calls = []

    async def flaky(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise ledger.LedgerUnavailable("ledger down")
        return await real(*args, **kwargs)
    monkeypatch.setattr(ledger, "record_platform_health", flaky)
    assert (await selfheal.run_sweep_once(db, now=at(t0, 400)))["alarmed"] is False
    assert await _state(db) is None and await _notices(db) == []
    assert (await selfheal.run_sweep_once(db, now=at(t0, 460)))["alarmed"] is True
    assert len(await _rows(db, "watchdog_silent")) == 1 and len(await _notices(db)) == 1


async def test_the_sync_door_ends_the_silence_and_the_panel_shows_both_rows(world):
    start = datetime.now(timezone.utc) - timedelta(hours=1)
    await selfheal.record_heartbeat(world.db, "omni", start)
    assert (await selfheal.run_sweep_once(world.db))["alarmed"] is True                         # real clock: an hour of silence
    assert (await world.summary())["watchdog"] == "silent"
    await world.sync()
    assert (await world.summary())["watchdog"] == "running"
    items = (await world.get(ACTIONS)).json()["items"]
    texts = {row["reasonText"]: row for row in items}
    assert any(t.startswith("No heartbeat for 60 minutes") or t.startswith("No heartbeat for 59 minutes") for t in texts)
    assert "Heartbeat resumed." in texts and texts["Heartbeat resumed."]["resultText"] == "Reporting again."
    assert await world.db.oncall_outbox.count_documents({}) == 0


async def test_the_loop_survives_a_failed_pass_and_keeps_sweeping(db, monkeypatch):
    import database
    monkeypatch.setattr(database, "get_database", lambda: db)
    monkeypatch.setattr(selfheal, "SWEEP_EVERY", 0.01)
    calls = []

    async def flaky(_db, *, now=None):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("database fell over")
    monkeypatch.setattr(selfheal, "run_sweep_once", flaky)
    task = asyncio.create_task(selfheal.selfheal_loop())
    for _ in range(100):
        if len(calls) >= 3:
            break
        await asyncio.sleep(0.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(calls) >= 3


def test_the_loop_is_registered_at_startup_and_the_alarm_never_uses_the_oncall_queue():
    here = os.path.dirname(__file__)
    startup = open(os.path.join(here, "..", "app_startup.py"), encoding="utf-8").read()
    assert "selfheal_loop" in startup and 'name="autonomous_ops_selfheal"' in startup
    source = open(os.path.join(here, "..", "autonomous_ops", "selfheal.py"), encoding="utf-8").read()
    assert "notify(" not in source and "oncall.enqueue" not in source and "enqueue(" not in source
