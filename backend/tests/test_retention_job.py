"""Scheduled retention job (phase 82, plan 09): the first run only counts.

Real-Mongo cases use the throwaway database from tests/_mongo_test_db.py (set MONGO_TEST_URL to a
private mongod; never the live one) and skip when no server is reachable.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-retention-job")

from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_tenant

import retention_gate as gate
import retention_job as job

NOW = datetime(2026, 10, 27, 9, 0, 0, tzinfo=timezone.utc)


def oid(days_ago, seconds=0, *, now=NOW):
    """A unique ObjectId created ``days_ago`` days (plus ``seconds``) before ``now``."""
    stamp = ObjectId.from_datetime(now - timedelta(days=days_ago, seconds=seconds)).binary[:4]
    return ObjectId(stamp + os.urandom(8))


async def _seed_metrics(db, tenant_id, *, old=3, new=2, field="tenant_id", collection="agent_metrics"):
    docs = [{"_id": oid(40, seconds=i), field: tenant_id, "n": i} for i in range(old)]
    docs += [{"_id": oid(5, seconds=i), field: tenant_id, "n": 100 + i} for i in range(new)]
    if docs:
        await db[collection].insert_many(docs)


# ------------------------------------------------------------------ Task 1: the tracer

@pytest.mark.asyncio
async def test_first_run_counts_old_agent_metrics_and_deletes_nothing(mongo_db):
    await seed_tenant(mongo_db, "t1")
    await _seed_metrics(mongo_db, "t1")

    summary = await job.run_all(mongo_db, now=NOW, trigger="scheduled")

    assert await mongo_db.agent_metrics.count_documents({}) == 5
    count = await mongo_db.retention_counts.find_one({"tenantId": "t1", "type": "agent_metrics"}, {"_id": 0})
    assert count["days"] == 30 and count["count"] == 3 and count["error"] is None
    assert count["countedAt"] is not None
    run = await mongo_db.retention_job_runs.find_one({}, {"_id": 0})
    assert (run["trigger"], run["counted"], run["deleted"], run["tenants"]) == ("scheduled", 3, 0, 1)
    assert summary["counted"] == 3 and summary["deleted"] == 0
    row = await mongo_db.retention_gate.find_one({"tenantId": "t1", "type": "agent_metrics"})
    assert row["confirmedDays"] is None and row["firstSeenAt"] is not None


@pytest.mark.asyncio
async def test_every_registry_type_gets_a_gate_row_and_a_count_row(mongo_db):
    await seed_tenant(mongo_db, "t1")
    await job.run_all(mongo_db, now=NOW, trigger="scheduled")
    assert {r["type"] async for r in mongo_db.retention_gate.find({"tenantId": "t1"})} == set(gate.TYPE_IDS)
    assert {r["type"] async for r in mongo_db.retention_counts.find({"tenantId": "t1"})} == set(gate.TYPE_IDS)


def test_registry_is_the_eight_types_and_disjoint_from_never_deleted():
    assert gate.TYPE_IDS == ("metrics", "notifications", "agent_location_history", "agent_uptime_rollups",
                             "agent_metrics", "asset_metrics", "persistence_results", "logs")
    assert not {t.collection for t in gate.RETENTION_TYPES} & gate.NEVER_DELETED
    for name in ("audit_logs", "audit_chain_heads", "audit_chain_checkpoints", "autonomy_actions",
                 "autonomy_settings", "autonomy_never_touch", "compliance_evidence"):
        assert name in gate.NEVER_DELETED
    by = gate.BY_ID
    assert (by["agent_uptime_rollups"].tenant_field, by["agent_metrics"].tenant_field,
            by["asset_metrics"].tenant_field, by["persistence_results"].tenant_field) == \
        ("tenant_id", "tenant_id", "tenant_id", "tenantId")
    assert [t.default_days for t in gate.RETENTION_TYPES] == [30, 30, 365, 90, 30, 30, 90, 30]


def test_module_boundary_keeps_retention_service_out():
    import ast
    for name in ("retention_gate.py", "retention_job.py"):
        tree = ast.parse(open(os.path.join(os.path.dirname(__file__), "..", name), encoding="utf-8").read())
        for node in ast.walk(tree):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            assert not any("retention_service" in n for n in names), name


# ------------------------------------------------------------------ Task 2: gate, confirmation, bounded deletes

class _SpyColl:
    def __init__(self, coll, log):
        self._c, self._log = coll, log

    def __getattr__(self, name):
        return getattr(self._c, name)

    async def delete_many(self, flt, *args, **kwargs):
        self._log.append((self._c.name, len(flt["_id"]["$in"])))
        return await self._c.delete_many(flt, *args, **kwargs)


class _SpyDb:
    """A raw database whose delete_many calls are recorded as (collection, batch size)."""

    def __init__(self, db):
        self._db, self.log = db, []

    def __getitem__(self, name):
        return _SpyColl(self._db[name], self.log)

    def __getattr__(self, name):
        return self[name]


async def _confirm_all(db, now=NOW):
    rows = await gate.review_rows(db)
    return await gate.confirm(db, gate.review_token(rows), "Super Admin", now)


@pytest.fixture
def pauses(monkeypatch):
    calls = []

    async def fake_sleep(seconds):
        calls.append(seconds)

    monkeypatch.setattr(job, "_sleep", fake_sleep)
    return calls


@pytest.mark.asyncio
async def test_confirmed_run_deletes_only_old_records_and_keeps_new_ones(mongo_db, pauses):
    await seed_tenant(mongo_db, "t1")
    await _seed_metrics(mongo_db, "t1")
    await job.run_all(mongo_db, now=NOW)
    await _confirm_all(mongo_db)
    assert await mongo_db.agent_metrics.count_documents({}) == 5          # confirming deletes nothing

    summary = await job.run_all(mongo_db, now=NOW + timedelta(minutes=1))

    assert summary["deleted"] == 3 and summary["counted"] == 0
    left = [d["n"] async for d in mongo_db.agent_metrics.find({}).sort("n", 1)]
    assert left == [100, 101]
    row = await mongo_db.retention_gate.find_one({"tenantId": "t1", "type": "agent_metrics"})
    assert row["confirmedDays"] == 30


@pytest.mark.asyncio
async def test_batches_of_500_500_200_with_a_pause_between_them(mongo_db, pauses):
    await seed_tenant(mongo_db, "t1")
    await mongo_db.agent_metrics.insert_many(
        [{"_id": oid(40, i), "tenant_id": "t1"} for i in range(1200)]
        + [{"_id": oid(1, i), "tenant_id": "t1"} for i in range(7)])
    await job.run_all(mongo_db, now=NOW)
    await _confirm_all(mongo_db)

    spy = _SpyDb(mongo_db)
    summary = await job.run_all(spy, now=NOW + timedelta(minutes=1))

    assert [n for coll, n in spy.log if coll == "agent_metrics"] == [500, 500, 200]
    assert pauses == [job.PAUSE_SECONDS, job.PAUSE_SECONDS]
    assert job.BATCH_SIZE == 500 and job.PAUSE_SECONDS == 0.5 and job.RUN_MAX_MINUTES == 60
    assert summary["deleted"] == 1200 and await mongo_db.agent_metrics.count_documents({}) == 7


@pytest.mark.asyncio
async def test_batch_size_and_pause_are_configurable(mongo_db, pauses, monkeypatch):
    monkeypatch.setattr(job, "BATCH_SIZE", 2)
    monkeypatch.setattr(job, "PAUSE_SECONDS", 0.01)
    await seed_tenant(mongo_db, "t1")
    await _seed_metrics(mongo_db, "t1", old=5, new=0)
    await job.run_all(mongo_db, now=NOW)
    await _confirm_all(mongo_db)
    spy = _SpyDb(mongo_db)
    await job.run_all(spy, now=NOW + timedelta(minutes=1))
    assert [n for coll, n in spy.log if coll == "agent_metrics"] == [2, 2, 1]
    assert pauses == [0.01, 0.01]


def test_environment_overrides_fall_back_on_bad_values(monkeypatch):
    monkeypatch.setenv("RETENTION_BATCH_SIZE", "250")
    monkeypatch.setenv("RETENTION_BATCH_PAUSE_SECONDS", "nope")
    monkeypatch.setenv("RETENTION_RUN_MAX_MINUTES", "-3")
    assert job._env_number("RETENTION_BATCH_SIZE", 500, int) == 250
    assert job._env_number("RETENTION_BATCH_PAUSE_SECONDS", 0.5, float) == 0.5
    assert job._env_number("RETENTION_RUN_MAX_MINUTES", 60, int) == 60


@pytest.mark.asyncio
async def test_a_lost_lock_after_the_first_batch_stops_the_run(mongo_db, monkeypatch):
    monkeypatch.setattr(job, "BATCH_SIZE", 2)
    state = {"lost": False}

    async def losing_sleep(seconds):
        state["lost"] = True

    monkeypatch.setattr(job, "_sleep", losing_sleep)
    await seed_tenant(mongo_db, "t1")
    await _seed_metrics(mongo_db, "t1", old=5, new=1)
    await job.run_all(mongo_db, now=NOW)
    await _confirm_all(mongo_db)

    summary = await job.run_all(mongo_db, now=NOW + timedelta(minutes=1), lost=lambda: state["lost"])

    assert summary["stoppedEarly"] is True and summary["deleted"] == 2
    assert await mongo_db.agent_metrics.count_documents({}) == 4
    run = await mongo_db.retention_job_runs.find_one({}, sort=[("startedAt", -1)])
    assert run["stoppedEarly"] is True


@pytest.mark.asyncio
async def test_the_wall_clock_cap_stops_the_run_and_records_it(mongo_db, pauses, monkeypatch):
    await seed_tenant(mongo_db, "t1")
    await _seed_metrics(mongo_db, "t1")
    await job.run_all(mongo_db, now=NOW)
    await _confirm_all(mongo_db)
    result = await job.delete_type(mongo_db, gate.BY_ID["agent_metrics"], "t1", 30, NOW,
                                   deadline=job.time.monotonic() - 1)
    assert result == {"deleted": 0, "stoppedEarly": True}
    monkeypatch.setattr(job, "RUN_MAX_MINUTES", 0.0000001)                # deadline passes at once
    summary = await job.run_all(mongo_db, now=NOW + timedelta(minutes=1))
    assert summary["stoppedEarly"] is True and summary["deleted"] == 0
    assert await mongo_db.agent_metrics.count_documents({}) == 5


@pytest.mark.asyncio
async def test_audit_and_decision_records_are_untouched_by_a_confirmed_run(mongo_db, pauses):
    await seed_tenant(mongo_db, "t1")
    old_iso = (NOW - timedelta(days=4000)).isoformat()
    old_date = NOW - timedelta(days=4000)
    for name in sorted(gate.NEVER_DELETED):
        await mongo_db[name].insert_many([
            {"_id": oid(4000, i), "tenantId": "t1", "tenant_id": "t1", "timestamp": old_iso,
             "sent_at": old_iso, "at": old_date} for i in range(3)])
    await _seed_metrics(mongo_db, "t1")
    before = {name: {d["_id"] async for d in mongo_db[name].find({}, {"_id": 1})} for name in gate.NEVER_DELETED}
    assert all(len(ids) >= 3 for ids in before.values())
    await job.run_all(mongo_db, now=NOW)
    await _confirm_all(mongo_db)
    summary = await job.run_all(mongo_db, now=NOW + timedelta(minutes=1))
    assert summary["deleted"] == 3
    # a scheduled run may add its own Activity and audit rows (82-10); it never removes an existing one
    for name in gate.NEVER_DELETED:
        after = {d["_id"] async for d in mongo_db[name].find({}, {"_id": 1})}
        assert before[name] <= after, name


@pytest.mark.asyncio
async def test_delete_type_refuses_a_protected_collection(mongo_db):
    bad = gate.RetentionType("x", "audit_logs", "tenantId", "iso", "timestamp", 30, "X")
    with pytest.raises(RuntimeError):
        await job.delete_type(mongo_db, bad, "t1", 30, NOW)


@pytest.mark.asyncio
async def test_uptime_rollups_use_tenant_id_and_never_cross_tenants(mongo_db, pauses):
    await seed_tenant(mongo_db, "t1")
    await seed_tenant(mongo_db, "t2")
    old = NOW - timedelta(days=200)
    await mongo_db.agent_uptime_rollups.insert_many([
        {"tenant_id": "t1", "timestamp": old, "k": "t1-old"},
        {"tenant_id": "t1", "timestamp": NOW - timedelta(days=1), "k": "t1-new"},
        {"tenant_id": "t2", "timestamp": old, "k": "t2-old"},
        {"tenantId": "t1", "timestamp": old, "k": "wrong-field"},          # not the stored tenant field
    ])
    await job.run_all(mongo_db, now=NOW)
    await _confirm_all(mongo_db)

    await job.run_tenant(mongo_db, "t1", now=NOW + timedelta(minutes=1))

    keys = {d["k"] async for d in mongo_db.agent_uptime_rollups.find({})}
    assert keys == {"t1-new", "t2-old", "wrong-field"}


@pytest.mark.asyncio
async def test_a_shortened_period_sends_only_that_tenant_and_type_back_to_counting(mongo_db, pauses):
    for tid in ("t1", "t2"):
        await seed_tenant(mongo_db, tid)
        await _seed_metrics(mongo_db, tid)
        await mongo_db.logs.insert_many([{"_id": oid(40, i), "tenantId": tid} for i in range(2)])
    await job.run_all(mongo_db, now=NOW)
    await _confirm_all(mongo_db)
    await mongo_db.agent_metrics.insert_many([{"_id": oid(25, i), "tenant_id": "t1"} for i in range(4)])
    await mongo_db.retention_policies.insert_one(
        {"tenantId": "t1", "collection": "agent_metrics", "retention_days": 20})

    summary = await job.run_all(mongo_db, now=NOW + timedelta(minutes=1))

    # t1/agent_metrics only counts (3 at 40 days + 4 at 25 days are older than 20): nothing deleted
    assert await mongo_db.agent_metrics.count_documents({"tenant_id": "t1"}) == 9
    assert await mongo_db.agent_metrics.count_documents({"tenant_id": "t2"}) == 2      # t2 deleted its 3
    assert await mongo_db.logs.count_documents({}) == 0                                # both tenants' logs
    count = await mongo_db.retention_counts.find_one({"tenantId": "t1", "type": "agent_metrics"})
    assert (count["days"], count["count"]) == (20, 7)
    assert summary["counted"] == 7 and summary["deleted"] == 3 + 4


@pytest.mark.asyncio
async def test_a_lengthened_period_is_adopted_without_review(mongo_db, pauses):
    await seed_tenant(mongo_db, "t1")
    await mongo_db.agent_metrics.insert_many(
        [{"_id": oid(40, 0), "tenant_id": "t1", "n": 1}, {"_id": oid(70, 0), "tenant_id": "t1", "n": 2}])
    await job.run_all(mongo_db, now=NOW)
    await _confirm_all(mongo_db)
    await mongo_db.retention_policies.insert_one(
        {"tenantId": "t1", "collection": "agent_metrics", "retention_days": 60})

    await job.run_all(mongo_db, now=NOW + timedelta(minutes=1))

    assert [d["n"] async for d in mongo_db.agent_metrics.find({})] == [1]              # 70 days gone, 40 kept
    row = await mongo_db.retention_gate.find_one({"tenantId": "t1", "type": "agent_metrics"})
    assert row["confirmedDays"] == 60
    assert await gate.review_rows(mongo_db) == []
    await mongo_db.retention_policies.update_one({"tenantId": "t1"}, {"$set": {"retention_days": 45}})
    rows = await gate.review_rows(mongo_db)
    assert [(r["type"], r["previousDays"], r["days"], r["reason"]) for r in rows] == \
        [("agent_metrics", 60, 45, "shortened")]


@pytest.mark.asyncio
async def test_a_tenant_created_after_the_confirmation_is_adopted_and_deletes(mongo_db, pauses):
    await seed_tenant(mongo_db, "t1")
    await job.run_all(mongo_db, now=NOW)
    await _confirm_all(mongo_db)
    await seed_tenant(mongo_db, "t-new")
    await mongo_db.tenants.update_one({"id": "t-new"}, {"$set": {"createdAt": (NOW + timedelta(hours=1)).isoformat()}})
    await _seed_metrics(mongo_db, "t-new")

    await job.run_all(mongo_db, now=NOW + timedelta(days=1))

    assert await mongo_db.agent_metrics.count_documents({"tenant_id": "t-new"}) == 2
    assert await gate.review_rows(mongo_db) == []


@pytest.mark.asyncio
async def test_boundary_a_record_exactly_retention_days_old_is_kept(mongo_db):
    cutoff = NOW - timedelta(days=30)
    await mongo_db.agent_metrics.insert_many([
        {"_id": ObjectId.from_datetime(cutoff), "tenant_id": "t1"},                       # exactly 30 days
        {"_id": ObjectId.from_datetime(cutoff - timedelta(seconds=1)), "tenant_id": "t1"}])
    await mongo_db.notifications.insert_many([
        {"tenantId": "t1", "sent_at": cutoff.isoformat()},
        {"tenantId": "t1", "sent_at": (cutoff - timedelta(seconds=1)).isoformat()}])
    await mongo_db.agent_uptime_rollups.insert_many([
        {"tenant_id": "t1", "timestamp": NOW - timedelta(days=90)},
        {"tenant_id": "t1", "timestamp": NOW - timedelta(days=90, seconds=1)}])
    await mongo_db.agent_location_history.insert_many([
        {"tenantId": "t1", "timestamp": NOW - timedelta(days=365)},
        {"tenantId": "t1", "timestamp": NOW - timedelta(days=365, seconds=1)}])
    for type_id, days in (("agent_metrics", 30), ("notifications", 30), ("agent_uptime_rollups", 90),
                          ("agent_location_history", 365)):
        assert await job.count_type(mongo_db, gate.BY_ID[type_id], "t1", days, NOW) == 1, type_id


# ------------------------------------------------------------------ Task 3: schedule, lock, wiring

def _utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


@pytest.mark.parametrize("now,expected", [
    (_utc(2026, 10, 27, 1, 59, 59), _utc(2026, 10, 27, 2, 0, 0)),
    (_utc(2026, 10, 27, 2, 0, 0), _utc(2026, 10, 28, 2, 0, 0)),
    (_utc(2026, 10, 27, 23, 0, 0), _utc(2026, 10, 28, 2, 0, 0)),
    (_utc(2026, 12, 31, 23, 0, 0), _utc(2027, 1, 1, 2, 0, 0)),
    (datetime(2026, 10, 27, 0, 30), _utc(2026, 10, 27, 2, 0, 0)),             # naive means UTC
])
def test_next_scheduled_is_the_next_0200_utc_strictly_after_now(now, expected):
    assert job.next_scheduled(now) == expected


@pytest.mark.parametrize("now,last,expected", [
    (_utc(2026, 10, 27, 2, 0), None, True),
    (_utc(2026, 10, 27, 1, 59), None, False),
    (_utc(2026, 10, 27, 9, 0), None, True),                                    # catch-up after an outage
    (_utc(2026, 10, 27, 9, 0), datetime(2026, 10, 27).date(), False),
    (_utc(2026, 10, 27, 9, 0), datetime(2026, 10, 26).date(), True),
    (_utc(2026, 10, 27, 1, 0), datetime(2026, 10, 26).date(), False),
])
def test_due(now, last, expected):
    assert job.due(now, last) is expected


@pytest.mark.asyncio
async def test_run_once_runs_once_per_day_under_the_lock(mongo_db, pauses):
    await seed_tenant(mongo_db, "t1")
    first = await job.run_once(mongo_db, now=_utc(2026, 10, 27, 2, 5))
    assert first is not None and first["trigger"] == "scheduled" and first["tenants"] == 1
    assert await job.run_once(mongo_db, now=_utc(2026, 10, 27, 9, 0)) is None
    assert await mongo_db.retention_job_runs.count_documents({}) == 1
    nxt = await job.run_once(mongo_db, now=_utc(2026, 10, 28, 3, 0))
    assert nxt is not None and await mongo_db.retention_job_runs.count_documents({}) == 2


@pytest.mark.asyncio
async def test_run_once_before_0200_does_nothing(mongo_db, pauses):
    await seed_tenant(mongo_db, "t1")
    assert await job.run_once(mongo_db, now=_utc(2026, 10, 27, 1, 59)) is None
    assert await mongo_db.retention_job_runs.count_documents({}) == 0


@pytest.mark.asyncio
async def test_a_second_runner_returns_none_while_the_lock_is_held(mongo_db, pauses):
    from types import SimpleNamespace
    import distributed_lock
    await seed_tenant(mongo_db, "t1")
    token = await distributed_lock.acquire_lock(SimpleNamespace(_db=mongo_db), job.LOCK_NAME, 120)
    assert token is not None
    assert await job.run_once(mongo_db, now=_utc(2026, 10, 27, 9, 0)) is None
    assert await job.run_manual(mongo_db, "t1", now=_utc(2026, 10, 27, 9, 0)) is None
    assert await mongo_db.retention_job_runs.count_documents({}) == 0
    await distributed_lock.release_lock(SimpleNamespace(_db=mongo_db), job.LOCK_NAME, token)
    assert await job.run_once(mongo_db, now=_utc(2026, 10, 27, 9, 0)) is not None


@pytest.mark.asyncio
async def test_a_manual_run_does_not_count_as_the_days_scheduled_run(mongo_db, pauses):
    await seed_tenant(mongo_db, "t1")
    await seed_tenant(mongo_db, "t2")
    manual = await job.run_manual(mongo_db, "t1", now=_utc(2026, 10, 27, 9, 0))
    assert manual["trigger"] == "manual" and manual["tenants"] == 1 and manual["tenantId"] == "t1"
    assert await mongo_db.retention_gate.count_documents({"tenantId": "t2"}) == 0       # only t1 was touched
    scheduled = await job.run_once(mongo_db, now=_utc(2026, 10, 27, 9, 30))
    assert scheduled is not None and scheduled["tenants"] == 2


@pytest.mark.asyncio
async def test_the_platform_stop_does_not_pause_retention(mongo_db, pauses):
    from tests.autonomy_support import seed_platform_stop
    await seed_tenant(mongo_db, "t1")
    await seed_platform_stop(mongo_db, active=True)
    assert await job.run_once(mongo_db, now=_utc(2026, 10, 27, 9, 0)) is not None


@pytest.mark.asyncio
async def test_retention_loop_survives_a_failed_pass_and_stops_on_cancel(monkeypatch):
    import asyncio
    import types
    monkeypatch.setitem(sys.modules, "database", types.SimpleNamespace(get_database=lambda: object()))
    calls = {"n": 0}

    async def flaky(db, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        raise asyncio.CancelledError()

    async def no_sleep(seconds):
        return None

    monkeypatch.setattr(job, "run_once", flaky)
    monkeypatch.setattr(job.asyncio, "sleep", no_sleep)
    with pytest.raises(asyncio.CancelledError):
        await job.retention_loop()
    assert calls["n"] == 2
    assert job.WAKE_EVERY == 300 and job.LOCK_NAME == "retention_job"


def test_the_telemetry_loop_is_gone_and_retention_loop_is_registered():
    here = os.path.join(os.path.dirname(__file__), "..")
    for name in ("app_background_tasks.py", "app_startup.py"):
        assert "agent_telemetry_retention_loop" not in open(os.path.join(here, name), encoding="utf-8").read()
    startup = open(os.path.join(here, "app_startup.py"), encoding="utf-8").read()
    assert "retention_loop" in startup and '"retention_job"' in startup
