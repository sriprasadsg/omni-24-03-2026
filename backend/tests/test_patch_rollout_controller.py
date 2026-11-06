"""Staged patch rollouts, plan 84-22: migration 031 and the controller loop around ``controller.tick``.

Real MongoDB (skips without one) through the throwaway database of tests/_mongo_test_db.py. The migration is
only ever run against that throwaway database.

Value: protects=PTCH-07 / PTCH-01: the index that keeps a computer in one rollout exists on live before the
controller acts, a repeat run changes nothing, one controller runs at a time, nothing runs without the claim
index, and a restart picks a rollout up from what is stored; fails_when=the migration backfills or deletes a
document, a second run changes an index, two controllers tick together, a tick runs while duplicate active
claims exist, a restart writes a second instruction, or a failing pass ends the loop;
no_claim=a real restart of the backend or the live database.
"""
import asyncio
import importlib
import logging
import os
import sys
from datetime import timedelta
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autonomous_ops import protected
from autonomous_ops.rollout import LOCK_NAME, controller, loop
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.test_patch_rollout_tracer import NOW, T, begin, instructions, rows, world

CLAIM_INDEX = "one_active_rollout_per_host"

migration = importlib.import_module("migrations.031_patch_rollouts")


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_REMEDIATION_DRY_RUN", "false")
    protected.cache_clear()


async def _definitions(db, collection):
    info = await db[collection].index_information()
    return {name: {k: v for k, v in spec.items() if k != "v"} for name, spec in info.items()}


# ---------------------------------------------------------------- Task 1: migration 031

async def test_migration_creates_the_claim_index_and_the_lookups(mongo_db):
    await migration.up(mongo_db)
    claims = await _definitions(mongo_db, "patch_rollout_hosts")
    claim = claims["one_active_rollout_per_host"]
    assert claim["unique"] is True and claim["partialFilterExpression"] == {"active": True}
    assert [k for k, _ in claim["key"]] == ["tenantId", "agentId"]
    assert [k for k, _ in claims["tenant_rollout_ring"]["key"]] == ["tenantId", "rolloutId", "ring"]
    assert [k for k, _ in (await _definitions(mongo_db, "patch_rollouts"))["tenant_status"]["key"]] \
        == ["tenantId", "status"]


async def test_running_the_migration_twice_changes_no_index(mongo_db):
    await migration.up(mongo_db)
    first = {c: await _definitions(mongo_db, c) for c in ("patch_rollouts", "patch_rollout_hosts")}
    await migration.up(mongo_db)
    second = {c: await _definitions(mongo_db, c) for c in first}
    assert first == second


async def test_the_migration_backfills_and_deletes_nothing(mongo_db):
    rollout = {"id": "r1", "tenantId": "t1", "status": "running", "rings": [{"key": "canary"}]}
    host = {"tenantId": "t1", "rolloutId": "r1", "agentId": "a1", "ring": 0, "active": True, "state": "waiting"}
    await mongo_db.patch_rollouts.insert_one(dict(rollout))
    await mongo_db.patch_rollout_hosts.insert_one(dict(host))
    await migration.up(mongo_db)
    await migration.up(mongo_db)
    assert await mongo_db.patch_rollouts.count_documents({}) == 1
    assert await mongo_db.patch_rollout_hosts.count_documents({}) == 1
    assert await mongo_db.patch_rollouts.find_one({}, {"_id": 0}) == rollout
    assert await mongo_db.patch_rollout_hosts.find_one({}, {"_id": 0}) == host


def test_the_runner_discovers_migration_031():
    from migrations import runner
    assert dict(runner._discover_pending(set())).get("031") == "031_patch_rollouts"
    assert migration.DESCRIPTION


# ---------------------------------------------------------------- Task 2: the controller loop

@pytest.fixture
def ticks(monkeypatch):
    """Counts the calls ``controller.tick`` gets through ``loop.run_once``; the real tick still runs."""
    calls = []
    real = controller.tick

    async def counting(db, **kwargs):
        calls.append(kwargs)
        return await real(db, **kwargs)

    monkeypatch.setattr(controller, "tick", counting)
    return calls


async def test_a_held_lock_makes_run_once_return_none_and_run_no_tick(mongo_db, ticks):
    from distributed_lock import acquire_lock
    db = await world(mongo_db)
    await begin(db)
    assert await acquire_lock(SimpleNamespace(_db=mongo_db), LOCK_NAME, ttl_seconds=30)
    assert await loop.run_once(db, now=NOW) is None
    assert ticks == [] and await rows(db) == []


async def test_only_one_controller_ticks_at_a_time_and_the_lock_is_released(mongo_db, monkeypatch):
    db = await world(mongo_db)
    entered = []

    async def slow(db_, *, now=None, lost=None):
        entered.append(callable(lost))
        await asyncio.sleep(0.4)
        return {"tenants": 0}

    monkeypatch.setattr(controller, "tick", slow)
    results = await asyncio.gather(loop.run_once(db), loop.run_once(db))
    assert entered == [True] and results.count(None) == 1
    assert await loop.run_once(db) == {"tenants": 0}                       # released, so the next one proceeds
    assert await mongo_db["_distributed_locks"].count_documents({"_id": LOCK_NAME}) == 0


async def test_a_missing_claim_index_is_made_again_and_the_tick_runs(mongo_db, ticks):
    db = await world(mongo_db)
    await begin(db)
    await mongo_db.patch_rollout_hosts.drop_index(CLAIM_INDEX)
    counts = await loop.run_once(db, now=NOW)
    assert counts is not None and counts["tenants"] == 1 and len(ticks) == 1
    assert CLAIM_INDEX in await mongo_db.patch_rollout_hosts.index_information()


async def test_a_claim_index_that_cannot_be_made_stops_the_pass(mongo_db, ticks, caplog):
    db = await world(mongo_db)
    await begin(db)
    await mongo_db.patch_rollout_hosts.drop_index(CLAIM_INDEX)
    twin = {"tenantId": T, "rolloutId": "r-other", "agentId": "a1", "ring": 0, "active": True, "state": "waiting"}
    await mongo_db.patch_rollout_hosts.insert_many([dict(twin, rolloutId="r-x"), dict(twin, rolloutId="r-y")])
    with caplog.at_level(logging.ERROR):
        assert await loop.run_once(db, now=NOW) is None
    assert ticks == [] and await rows(db) == [] and await instructions(db) == []
    assert CLAIM_INDEX in caplog.text
    assert CLAIM_INDEX not in await mongo_db.patch_rollout_hosts.index_information()


def _reload_rollout_modules():
    """A backend restart as far as the code goes: every rollout module runs again from its file."""
    for name in ("messages", "store", "windows", "rings", "start", "dispatcher", "lines", "installs", "settle",
                 "health", "lifecycle", "controller", "loop"):
        importlib.reload(importlib.import_module(f"autonomous_ops.rollout.{name}"))


async def test_a_restart_resumes_the_rollout_from_stored_state_without_a_second_instruction(mongo_db):
    db = await world(mongo_db)
    rollout_id = await begin(db)
    assert await loop.run_once(db, now=NOW) is not None
    assert [h["state"] for h in await mongo_db.patch_rollout_hosts.find({"rolloutId": rollout_id}).to_list(5)] \
        == ["installing"]
    assert len(await instructions(db)) == 1 and len(await rows(db)) == 1

    _reload_rollout_modules()
    from autonomous_ops.rollout import loop as fresh_loop
    assert await fresh_loop.run_once(db, now=NOW + timedelta(seconds=30)) is not None

    rollout = await mongo_db.patch_rollouts.find_one({"id": rollout_id})
    host = await mongo_db.patch_rollout_hosts.find_one({"rolloutId": rollout_id})
    assert rollout["status"] == "running" and host["state"] == "installing"
    assert len(await instructions(db)) == 1 and len(await rows(db)) == 1


# ---------------------------------------------------------------- the loop and its interval

async def test_the_loop_logs_a_failing_pass_goes_on_and_re_raises_cancellation(monkeypatch, caplog):
    calls = []

    async def flaky(db, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("down")
        raise asyncio.CancelledError

    monkeypatch.setenv("PATCH_ROLLOUT_INTERVAL_SEC", "0.01")
    monkeypatch.setattr("database.get_database", lambda: object())
    monkeypatch.setattr(loop, "run_once", flaky)
    with caplog.at_level(logging.ERROR):
        with pytest.raises(asyncio.CancelledError):
            await loop.rollout_loop()
    assert len(calls) == 2 and "down" in caplog.text


def test_the_interval_reads_the_env_name_defaults_to_60_and_ignores_a_bad_value(monkeypatch):
    monkeypatch.delenv("PATCH_ROLLOUT_INTERVAL_SEC", raising=False)
    assert loop._interval() == 60
    monkeypatch.setenv("PATCH_ROLLOUT_INTERVAL_SEC", "5")
    assert loop._interval() == 5
    for bad in ("soon", "0", "-3", ""):
        monkeypatch.setenv("PATCH_ROLLOUT_INTERVAL_SEC", bad)
        assert loop._interval() == 60


def test_the_backend_starts_the_rollout_loop_beside_the_sweep():
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app_startup.py"),
               encoding="utf-8").read()
    assert "rollout_loop" in src and '"patch_rollout_controller"' in src
    assert src.index("autonomous_ops_sweep") < src.index("patch_rollout_controller")
