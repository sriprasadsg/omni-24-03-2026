"""CR-01 (phase 82, gap plan 82-15): a tenant the first pass never reached is counted, reviewed and
confirmed before anything of it is deleted; one tenant's failure never stops the pass; a confirmation
is refused while the counted set is incomplete.

Real Mongo through the throwaway database of tests/_mongo_test_db.py (MONGO_TEST_URL points at a
private mongod; never the live one).
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-retention-unreached")

from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_tenant

import retention_gate as gate
import retention_job as job

NOW = datetime(2026, 10, 27, 9, 0, 0, tzinfo=timezone.utc)
DAY = timedelta(days=1)


def oid(days_ago, seconds=0, *, now=NOW):
    """A unique ObjectId created ``days_ago`` days (plus ``seconds``) before ``now``."""
    stamp = ObjectId.from_datetime(now - timedelta(days=days_ago, seconds=seconds)).binary[:4]
    return ObjectId(stamp + os.urandom(8))


async def _seed_metrics(db, tenant_id, *, old=3, new=2, field="tenant_id", collection="agent_metrics"):
    docs = [{"_id": oid(40, seconds=i), field: tenant_id, "n": i} for i in range(old)]
    docs += [{"_id": oid(5, seconds=i), field: tenant_id, "n": 100 + i} for i in range(new)]
    if docs:
        await db[collection].insert_many(docs)


def lost_after(calls):
    """A ``lost`` callable that is False for its first ``calls`` calls and True afterwards. In a counting
    pass run_all calls it once per tenant and run_tenant once per type, so this stops a pass exactly."""
    state = {"n": 0}

    def lost():
        state["n"] += 1
        return state["n"] > calls

    return lost


async def confirm_directly(db, tenant_id, type_ids, at):
    """Confirm (tenant, types) straight in the database, the way an earlier confirmation would have."""
    for type_id in type_ids:
        await gate.set_confirmed_days(db, tenant_id, type_id, gate.BY_ID[type_id].default_days, at,
                                      actor="Super Admin")
    await db[gate.GATE_GLOBAL].update_one({"_id": gate.GLOBAL_ID}, {"$setOnInsert": {"confirmedAt": at}},
                                          upsert=True)


async def set_created(db, tenant_id, value):
    await db.tenants.update_one({"id": tenant_id}, {"$set": {"createdAt": value}})


async def confirm_all(db, now):
    rows = await gate.review_rows(db)
    return await gate.confirm(db, gate.review_token(rows), "Super Admin", now)


async def kept(db, tenant_id, collection="agent_metrics"):
    return await db[collection].count_documents({"tenant_id": tenant_id})


@pytest.fixture
def pauses(monkeypatch):
    async def fake_sleep(seconds):
        return None

    monkeypatch.setattr(job, "_sleep", fake_sleep)


# ------------------------------------------------------------------ Task 1: the tracer (CR-01)

@pytest.mark.asyncio
async def test_a_tenant_the_first_pass_never_reached_is_counted_then_confirmed_before_anything_is_deleted(
        mongo_db, pauses):
    for tid in ("t-a", "t-z"):
        await seed_tenant(mongo_db, tid)
        await _seed_metrics(mongo_db, tid)

    first = await job.run_all(mongo_db, now=NOW, lost=lost_after(9))
    assert first["tenants"] == 1 and first["stoppedEarly"] is True
    assert await mongo_db.retention_gate.count_documents({"tenantId": "t-z"}) == 0
    await confirm_directly(mongo_db, "t-a", gate.TYPE_IDS, NOW)

    await job.run_all(mongo_db, now=NOW + DAY)

    assert await kept(mongo_db, "t-a") == 2
    assert await kept(mongo_db, "t-z") == 5                       # nothing of the unreached tenant is deleted
    count = await mongo_db.retention_counts.find_one({"tenantId": "t-z", "type": "agent_metrics"})
    assert count["count"] == 3
    rows = await gate.review_rows(mongo_db)
    assert ("t-z", "agent_metrics", "first_run") in [(r["tenantId"], r["type"], r["reason"]) for r in rows]

    assert (await confirm_all(mongo_db, NOW + DAY))["tenants"] == 1
    await job.run_all(mongo_db, now=NOW + 2 * DAY)
    assert await kept(mongo_db, "t-z") == 2


@pytest.mark.asyncio
async def test_a_pass_that_stops_inside_one_tenant_leaves_its_other_types_counting(mongo_db, pauses):
    await seed_tenant(mongo_db, "t-a")
    await _seed_metrics(mongo_db, "t-a")

    await job.run_all(mongo_db, now=NOW, lost=lost_after(4))
    seen = {r["type"] async for r in mongo_db.retention_gate.find({"tenantId": "t-a"})}
    assert seen == set(gate.TYPE_IDS[:3])
    await confirm_directly(mongo_db, "t-a", gate.TYPE_IDS[:3], NOW)

    await job.run_all(mongo_db, now=NOW + DAY)

    assert await kept(mongo_db, "t-a") == 5
    count = await mongo_db.retention_counts.find_one({"tenantId": "t-a", "type": "agent_metrics"})
    assert count["count"] == 3


@pytest.mark.asyncio
async def test_a_data_type_with_no_gate_row_counts_for_an_existing_tenant(mongo_db, pauses):
    await seed_tenant(mongo_db, "t1")
    await set_created(mongo_db, "t1", NOW - timedelta(days=400))
    await _seed_metrics(mongo_db, "t1")
    await job.run_all(mongo_db, now=NOW)
    await confirm_all(mongo_db, NOW)
    for name in (gate.GATE, gate.COUNTS):                        # the type-added-later case
        await mongo_db[name].delete_many({"tenantId": "t1", "type": "agent_metrics"})

    await job.run_all(mongo_db, now=NOW + DAY)

    assert await kept(mongo_db, "t1") == 5
    rows = await gate.review_rows(mongo_db)
    assert [(r["tenantId"], r["type"], r["reason"]) for r in rows] == [("t1", "agent_metrics", "first_run")]


@pytest.mark.parametrize("value", ["absent", "not a time", 12345, None])
@pytest.mark.asyncio
async def test_an_unreadable_creation_time_is_never_adopted(mongo_db, pauses, value):
    for tid in ("t-a", "t-z"):
        await seed_tenant(mongo_db, tid)
        await _seed_metrics(mongo_db, tid)
    if value != "absent":
        await set_created(mongo_db, "t-z", value)

    await job.run_all(mongo_db, now=NOW, lost=lost_after(9))     # reaches only t-a: t-z has no gate rows
    assert await mongo_db.retention_gate.count_documents({"tenantId": "t-z"}) == 0
    await confirm_directly(mongo_db, "t-a", gate.TYPE_IDS, NOW)

    await job.run_all(mongo_db, now=NOW + DAY)

    assert await kept(mongo_db, "t-z") == 5
    count = await mongo_db.retention_counts.find_one({"tenantId": "t-z", "type": "agent_metrics"})
    assert count["count"] == 3


# ------------------------------------------------------------------ Task 2: HEAL-07, a failed tenant never reads as a clean run

def fail_for(monkeypatch, tenant_id, error):
    """load_policy_days raises ``error`` for ``tenant_id`` only; call inside monkeypatch.context()."""
    real = gate.load_policy_days

    async def flaky(db, tid):
        if tid == tenant_id:
            raise error
        return await real(db, tid)

    monkeypatch.setattr(gate, "load_policy_days", flaky)


async def three_tenants(db):
    for tid in ("t-a", "t-b", "t-c"):
        await seed_tenant(db, tid)


async def activity_row(db):
    return await db.autonomy_actions.find_one({"healthEvent": "retention_run"})


@pytest.mark.asyncio
async def test_one_tenant_raising_does_not_stop_the_later_tenants(mongo_db, pauses, monkeypatch):
    await three_tenants(mongo_db)
    with monkeypatch.context() as patch:
        fail_for(patch, "t-b", RuntimeError("mongo down"))
        summary = await job.run_all(mongo_db, now=NOW)

    assert summary["failedTenants"] == ["t-b"] and summary["tenants"] == 2
    assert "RuntimeError" in summary["error"] and "mongo down" in summary["error"]
    run = await mongo_db.retention_job_runs.find_one({})
    assert run["failedTenants"] == ["t-b"] and run["tenants"] == 2 and "RuntimeError" in run["error"]
    assert {r["type"] async for r in mongo_db.retention_gate.find({"tenantId": "t-c"})} == set(gate.TYPE_IDS)
    assert await mongo_db.retention_gate.count_documents({"tenantId": "t-b"}) == 0


@pytest.mark.asyncio
async def test_a_failed_tenant_makes_the_activity_row_critical(mongo_db, pauses, monkeypatch):
    await three_tenants(mongo_db)
    with monkeypatch.context() as patch:
        fail_for(patch, "t-b", RuntimeError("mongo down"))
        await job.run_all(mongo_db, now=NOW)

    row = await activity_row(mongo_db)
    assert row["healthParams"]["ok"] is False and "RuntimeError" in row["healthParams"]["error"]
    assert row["healthChip"] == "critical"


@pytest.mark.asyncio
async def test_a_clean_run_stores_no_failed_tenants_and_an_ok_activity_row(mongo_db, pauses):
    await three_tenants(mongo_db)
    summary = await job.run_all(mongo_db, now=NOW)

    assert summary["failedTenants"] == [] and summary["error"] is None
    assert (await mongo_db.retention_job_runs.find_one({}))["failedTenants"] == []
    row = await activity_row(mongo_db)
    assert row["healthParams"]["ok"] is True and row["healthChip"] == "healthy"


class _BrokenCursor:
    def find(self, *args, **kwargs):
        return self

    def sort(self, *args, **kwargs):
        return self

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise RuntimeError("cursor lost")


class _CursorDownDb:
    """A database that delegates everything except the tenants cursor, which fails on iteration."""

    def __init__(self, db):
        self._real = db

    def __getitem__(self, name):
        return self._real[name]

    def __getattr__(self, name):
        return _BrokenCursor() if name == "tenants" else getattr(self._real, name)


@pytest.mark.asyncio
async def test_a_tenants_cursor_failure_still_writes_the_run(mongo_db, pauses):
    await three_tenants(mongo_db)
    summary = await job.run_all(_CursorDownDb(mongo_db), now=NOW)

    assert summary["stoppedEarly"] is True and "cursor lost" in summary["error"]
    run = await mongo_db.retention_job_runs.find_one({})
    assert run["stoppedEarly"] is True and "cursor lost" in run["error"] and run["tenants"] == 0
    row = await activity_row(mongo_db)
    assert row["healthParams"]["ok"] is False and row["healthChip"] == "critical"


@pytest.mark.asyncio
async def test_cancellation_is_not_swallowed(mongo_db, pauses, monkeypatch):
    await three_tenants(mongo_db)
    with monkeypatch.context() as patch:
        fail_for(patch, "t-a", asyncio.CancelledError())
        with pytest.raises(asyncio.CancelledError):
            await job.run_all(mongo_db, now=NOW)

    assert await mongo_db.retention_job_runs.count_documents({}) == 0
    assert await activity_row(mongo_db) is None
