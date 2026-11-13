"""The daily digest loop (Phase 86, plan 86-05, ACTV-04, D-02): the 07:00 UTC schedule, the single-runner lock and
the once-per-day guarantee across repeated passes, parallel runners and a restart.

Value: protects=each ticked organization gets its digest from 07:00 UTC, once, and the loop survives a failing
organization, a held lock and a missing index; fails_when=a pass before 07:00 UTC writes anything, an unticked
organization or the platform organization gets a digest, a second pass, two parallel passes or a reloaded module
send a second one, or one organization's failure stops the others; no_claim=real mail and the live database.

Real MongoDB (never the live one): MONGO_TEST_URL, MONGODB_URL and MONGO_URI point at a private mongod.
"""
import asyncio
import importlib
import logging
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-the-digest-job")

from autonomous_ops.reporting import DIGESTS, digest, digest_job as job
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_tenant

UTC = timezone.utc
NOW = datetime(2026, 11, 12, 7, 5, tzinfo=UTC)


@pytest.fixture
def world(mongo_db, monkeypatch):
    monkeypatch.delenv("FRONTEND_URL", raising=False)
    job._indexes_ready_once = False
    return mongo_db


async def _ran_row(db, tenant, hour=5):
    await db.autonomy_actions.insert_one(
        {"id": "AO-" + uuid.uuid4().hex, "tenantId": tenant, "kind": "security", "command": "block_ip",
         "state": "executed", "reason": {"ruleId": "sweep:block_ip"}, "target": "203.0.113.7",
         "createdAt": datetime(2026, 11, 12, hour, tzinfo=UTC), "finishedAt": datetime(2026, 11, 12, hour, tzinfo=UTC)})


async def _three_tenants(db):
    for tenant in ("t1", "t2", "t3"):
        await seed_tenant(db, tenant)
    await seed_tenant(db, "t4", ticked=False)
    await seed_tenant(db, "platform-admin")
    for tenant in ("t1", "t2", "t4", "platform-admin"):      # t3 has nothing: a quiet day
        await _ran_row(db, tenant)


async def _notice_counts(db):
    return {t: await db.notifications.count_documents({"tenantId": t}) for t in ("t1", "t2", "t3", "t4", "platform-admin")}


def test_the_digest_is_due_from_07_00_utc():
    assert job.due(datetime(2026, 11, 12, 6, 59, 59, tzinfo=UTC)) is False
    assert job.due(datetime(2026, 11, 12, 7, 0, 0, tzinfo=UTC)) is True
    assert job.due(datetime(2026, 11, 12, 23, 59, tzinfo=UTC)) is True
    assert job.due(datetime(2026, 11, 12, 8, 30, tzinfo=timezone(timedelta(hours=5)))) is False   # 03:30 UTC


def test_the_loop_constants_match_the_plan():
    assert (job.LOCK_NAME, job.WAKE_EVERY, job.STARTUP_DELAY) == ("autonomous_ops_digest", 300, 120)


async def test_a_pass_before_07_00_sends_nothing_and_writes_no_claim(world):
    await _three_tenants(world)
    assert await job.run_once(world, now=datetime(2026, 11, 12, 6, 59, 59, tzinfo=UTC)) is None
    assert await world[DIGESTS].count_documents({}) == 0
    assert set((await _notice_counts(world)).values()) == {0}


async def test_a_pass_after_07_00_digests_each_ticked_organization_once(world):
    await _three_tenants(world)
    assert await job.run_once(world, now=NOW) == {"sent": 2, "quiet": 1, "skipped": 0, "failed": 0}
    claims = {c["tenantId"]: c["state"] async for c in world[DIGESTS].find({"day": "2026-11-12"})}
    assert claims == {"t1": "sent", "t2": "sent", "t3": "quiet"}
    assert await _notice_counts(world) == {"t1": 1, "t2": 1, "t3": 0, "t4": 0, "platform-admin": 0}


async def test_a_second_pass_a_parallel_pass_and_a_restart_send_nothing_new(world):
    await _three_tenants(world)
    await job.run_once(world, now=NOW)
    assert await job.run_once(world, now=NOW + timedelta(minutes=5)) == {"sent": 0, "quiet": 0, "skipped": 0, "failed": 0}
    reloaded = importlib.reload(job)
    try:
        await reloaded.run_once(world, now=NOW + timedelta(minutes=10))
        assert (await _notice_counts(world))["t1"] == 1
        # the next day: two runners started together send one notice per organization
        tomorrow = NOW + timedelta(days=1)
        for tenant in ("t1", "t2"):
            await world.autonomy_actions.insert_one(
                {"id": "AO-" + uuid.uuid4().hex, "tenantId": tenant, "kind": "security", "command": "block_ip", "state": "executed",
                 "reason": {"ruleId": "sweep:block_ip"}, "createdAt": tomorrow - timedelta(hours=3),
                 "finishedAt": tomorrow - timedelta(hours=3)})
        await asyncio.gather(reloaded.run_once(world, now=tomorrow), reloaded.run_once(world, now=tomorrow))
        assert await _notice_counts(world) == {"t1": 2, "t2": 2, "t3": 0, "t4": 0, "platform-admin": 0}
    finally:
        importlib.reload(job)


async def test_a_pass_returns_none_while_another_holder_has_the_lock(world):
    await _three_tenants(world)
    await world["_distributed_locks"].insert_one({"_id": job.LOCK_NAME, "token": "other",
                                                   "expiresAt": datetime.now(UTC) + timedelta(hours=1)})
    assert await job.run_once(world, now=NOW) is None
    assert set((await _notice_counts(world)).values()) == {0} and await world[DIGESTS].count_documents({}) == 0


async def test_the_first_pass_makes_the_indexes_the_migration_may_not_have_made(world):
    await seed_tenant(world, "t1")
    assert "digest_once_per_day" not in await world[DIGESTS].index_information()
    await job.run_once(world, now=NOW)
    assert "digest_once_per_day" in await world[DIGESTS].index_information()
    assert "tenant_finished" in await world.autonomy_actions.index_information()


async def test_one_organizations_failure_never_stops_the_others(world):
    await _three_tenants(world)
    real = digest.send_for_tenant

    async def flaky(db, tenant, day, now):
        if tenant == "t1":
            raise RuntimeError("boom")
        return await real(db, tenant, day, now)

    with patch.object(digest, "send_for_tenant", flaky):
        assert await job.run_once(world, now=NOW) == {"sent": 1, "quiet": 1, "skipped": 0, "failed": 1}
    assert (await _notice_counts(world))["t2"] == 1
    assert await world[DIGESTS].count_documents({"tenantId": "t1"}) == 0     # released, so the next pass retries it
    assert (await job.run_once(world, now=NOW + timedelta(minutes=5)))["sent"] == 1


async def test_a_pass_that_cannot_make_its_index_does_not_run_unprotected(world):
    await _three_tenants(world)
    with patch.object(digest, "ensure_indexes", AsyncMock(side_effect=RuntimeError("duplicates"))):
        assert await job.run_once(world, now=NOW) is None
    assert set((await _notice_counts(world)).values()) == {0}


async def test_the_loop_waits_logs_once_and_runs_a_pass_every_wake(world, caplog):
    sleeps, passes = [], []

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) >= 4:
            raise asyncio.CancelledError

    async def one_pass(db):
        passes.append(db)
        if len(passes) == 2:
            raise RuntimeError("one bad pass")
        return {"sent": 0, "quiet": 0, "skipped": 0, "failed": 0}

    caplog.set_level(logging.INFO)
    with patch.object(job, "_sleep", fake_sleep), patch.object(job, "run_once", one_pass), \
            patch("database.get_database", lambda: world):
        with pytest.raises(asyncio.CancelledError):
            await job.digest_loop()
    assert sleeps == [120, 300, 300, 300] and len(passes) == 3
    started = [r for r in caplog.records if r.getMessage() == "autonomous_ops digest loop started"]
    assert len(started) == 1
    assert any("one bad pass" in r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR)


def test_the_loop_is_registered_at_startup_next_to_the_retention_loop():
    source = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app_startup.py")).read()
    assert "asyncio.create_task(_safe_bg_task(_digest_loop(), \"autonomous_ops_digest\"), name=\"autonomous_ops_digest\")" in source
    assert source.index("retention_loop as _retention_loop") < source.index("digest_loop as _digest_loop")
