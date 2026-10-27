"""Retention gate (phase 82, plan 09): states, review rows, the stale-review token, confirmation,
the policy loader and migration 027.

Real-Mongo cases use the throwaway database from tests/_mongo_test_db.py (MONGO_TEST_URL points at a
private mongod; the live one is never used) and skip when no server is reachable.
"""
import importlib
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-retention-gate")

from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_tenant

import retention_gate as gate
import retention_job as job

migration = importlib.import_module("migrations.027_retention_gate")

NOW = datetime(2026, 10, 27, 9, 0, 0, tzinfo=timezone.utc)
G = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)


def oid(days_ago, seconds=0):
    stamp = ObjectId.from_datetime(NOW - timedelta(days=days_ago, seconds=seconds)).binary[:4]
    return ObjectId(stamp + os.urandom(8))


async def _seed_old(db, tenant_id, collection="agent_metrics", field="tenant_id", old=3, new=2):
    docs = [{"_id": oid(40, i), field: tenant_id} for i in range(old)]
    docs += [{"_id": oid(5, i), field: tenant_id} for i in range(new)]
    await db[collection].insert_many(docs)


async def _confirm(db, actor="Super Admin", now=NOW):
    rows = await gate.review_rows(db)
    return await gate.confirm(db, gate.review_token(rows), actor, now)


# --------------------------------------------------------------------------- gate_state

@pytest.mark.parametrize("policy,confirmed,global_at,seen,expected", [
    (30, None, None, G, "first_run"),
    (30, None, G, G - timedelta(days=1), "first_run"),
    (30, None, G, G + timedelta(days=1), "adopt"),
    (30, None, G, G, "first_run"),
    (30, None, G, None, "first_run"),
    (30, 30, G, G, "confirmed"),
    (60, 30, G, G, "confirmed"),
    (20, 30, G, G, "shortened"),
    (29, 30, None, None, "shortened"),
    (30, 30, None, None, "confirmed"),
])
def test_gate_state_table(policy, confirmed, global_at, seen, expected):
    assert gate.gate_state(policy, confirmed, global_at, seen) == expected


def test_gate_state_accepts_naive_datetimes_as_mongo_returns_them():
    assert gate.gate_state(30, None, G.replace(tzinfo=None), (G + timedelta(hours=1))) == "adopt"
    assert gate.gate_state(30, None, G.replace(tzinfo=None), (G - timedelta(hours=1)).replace(tzinfo=None)) \
        == "first_run"


# --------------------------------------------------------------------------- policy loader

@pytest.mark.asyncio
async def test_load_policy_days_accepts_only_integer_days_in_range(mongo_db):
    await mongo_db.retention_policies.insert_many([
        {"tenantId": "t1", "collection": "agent_metrics", "retention_days": 20},
        {"tenantId": "t1", "collection": "logs", "retention_days": "7"},
        {"tenantId": "t1", "collection": "metrics", "retention_days": 0},
        {"tenantId": "t1", "collection": "notifications", "retention_days": 4000},
        {"tenantId": "t1", "collection": "agent_uptime_rollups", "retention_days": True},
        {"tenantId": "t1", "collection": "audit_logs", "retention_days": 5},         # not a registry type
        {"tenantId": "t1", "tier": "hot", "retention_days": 3},                      # retention_tiers shape
        {"tenantId": "t2", "collection": "logs", "retention_days": 9},
    ])
    assert await gate.load_policy_days(mongo_db, "t1") == {"agent_metrics": 20}
    assert await gate.load_policy_days(mongo_db, "t2") == {"logs": 9}


# --------------------------------------------------------------------------- review and confirm

@pytest.mark.asyncio
async def test_review_rows_shape_and_order(mongo_db):
    await seed_tenant(mongo_db, "ta", name="Alpha")
    await seed_tenant(mongo_db, "tb", name="Bravo")
    await _seed_old(mongo_db, "ta", old=1)
    await _seed_old(mongo_db, "tb", old=3)
    await job.run_all(mongo_db, now=NOW)
    rows = await gate.review_rows(mongo_db)
    assert len(rows) == 16
    top = rows[0]
    assert (top["tenantId"], top["type"], top["count"], top["days"], top["reason"]) == \
        ("tb", "agent_metrics", 3, 30, "first_run")
    assert set(top) == {"tenantId", "tenantName", "type", "label", "collection", "days", "previousDays",
                        "count", "countError", "countedAt", "reason"}
    assert top["tenantName"] == "Bravo" and top["label"] == "Agent metrics" and top["previousDays"] is None
    assert rows[1]["tenantId"] == "ta" and rows[1]["count"] == 1
    assert [r["count"] for r in rows] == sorted((r["count"] for r in rows), reverse=True)


@pytest.mark.asyncio
async def test_confirm_sets_confirmed_days_and_global_flag_but_deletes_nothing(mongo_db):
    await seed_tenant(mongo_db, "t1")
    await _seed_old(mongo_db, "t1")
    await job.run_all(mongo_db, now=NOW)
    result = await _confirm(mongo_db)
    assert result == {"rows": 8, "records": 3, "tenants": 1}
    assert await mongo_db.agent_metrics.count_documents({}) == 5
    assert await gate.global_confirmed_at(mongo_db) == NOW
    row = await mongo_db.retention_gate.find_one({"tenantId": "t1", "type": "agent_metrics"})
    assert row["confirmedDays"] == 30 and row["confirmedBy"] == "Super Admin"
    assert await gate.review_rows(mongo_db) == []


@pytest.mark.asyncio
async def test_a_second_confirm_does_not_move_the_global_confirmation(mongo_db):
    await seed_tenant(mongo_db, "t1")
    await job.run_all(mongo_db, now=NOW)
    await _confirm(mongo_db)
    await mongo_db.retention_policies.insert_one(
        {"tenantId": "t1", "collection": "logs", "retention_days": 10})
    await job.run_all(mongo_db, now=NOW + timedelta(days=1))
    rows = await gate.review_rows(mongo_db)
    assert [(r["type"], r["reason"], r["previousDays"]) for r in rows] == [("logs", "shortened", 30)]
    await gate.confirm(mongo_db, gate.review_token(rows), "Other Admin", NOW + timedelta(days=1))
    assert await gate.global_confirmed_at(mongo_db) == NOW


@pytest.mark.asyncio
async def test_confirm_with_a_token_from_before_a_recount_raises_and_changes_nothing(mongo_db):
    await seed_tenant(mongo_db, "t1")
    await _seed_old(mongo_db, "t1")
    await job.run_all(mongo_db, now=NOW)
    old_token = gate.review_token(await gate.review_rows(mongo_db))
    await mongo_db.agent_metrics.insert_one({"_id": oid(41), "tenant_id": "t1"})
    await job.run_all(mongo_db, now=NOW + timedelta(minutes=5))             # recount: 3 -> 4
    with pytest.raises(gate.StaleReview):
        await gate.confirm(mongo_db, old_token, "Super Admin", NOW)
    assert await mongo_db.retention_gate.count_documents({"confirmedDays": {"$ne": None}}) == 0
    assert await mongo_db.retention_gate_global.count_documents({}) == 0
    assert (await _confirm(mongo_db))["records"] == 4


@pytest.mark.asyncio
async def test_failed_counts_and_counts_at_another_period_are_not_confirmed(mongo_db):
    await seed_tenant(mongo_db, "t1")
    await _seed_old(mongo_db, "t1")
    await job.run_all(mongo_db, now=NOW)
    await mongo_db.retention_counts.update_one({"tenantId": "t1", "type": "logs"},
                                               {"$set": {"count": None, "error": "timed out"}})
    await mongo_db.retention_policies.insert_one(                           # period changed after counting
        {"tenantId": "t1", "collection": "metrics", "retention_days": 7})
    rows = {r["type"]: r for r in await gate.review_rows(mongo_db)}
    assert rows["logs"]["countError"] == "timed out" and rows["logs"]["count"] is None
    assert rows["metrics"]["count"] is None and rows["metrics"]["days"] == 7
    result = await _confirm(mongo_db)
    assert result["rows"] == 6
    left = {r["type"] for r in await gate.review_rows(mongo_db)}
    assert left == {"logs", "metrics"}
    assert await gate.global_confirmed_at(mongo_db) == NOW
    row = await mongo_db.retention_gate.find_one({"tenantId": "t1", "type": "logs"})
    assert row["confirmedDays"] is None


@pytest.mark.asyncio
async def test_shortening_twice_before_confirming_still_reports_the_confirmed_period(mongo_db):
    await seed_tenant(mongo_db, "t1")
    await job.run_all(mongo_db, now=NOW)
    await _confirm(mongo_db)
    pid = (await mongo_db.retention_policies.insert_one(
        {"tenantId": "t1", "collection": "persistence_results", "retention_days": 60})).inserted_id
    await job.run_all(mongo_db, now=NOW + timedelta(days=1))
    await mongo_db.retention_policies.update_one({"_id": pid}, {"$set": {"retention_days": 30}})
    await job.run_all(mongo_db, now=NOW + timedelta(days=2))
    rows = await gate.review_rows(mongo_db)
    assert [(r["type"], r["days"], r["previousDays"], r["reason"]) for r in rows] == \
        [("persistence_results", 30, 90, "shortened")]


@pytest.mark.asyncio
async def test_tenant_gate_flags(mongo_db):
    await seed_tenant(mongo_db, "t1")
    flags = await gate.tenant_gate_flags(mongo_db, "t1")
    assert set(flags) == set(gate.TYPE_IDS)
    assert all(f == {"waiting": True, "reason": "first_run"} for f in flags.values())
    await job.run_all(mongo_db, now=NOW)
    await _confirm(mongo_db, now=NOW - timedelta(days=30))
    await mongo_db.retention_policies.insert_one({"tenantId": "t1", "collection": "logs", "retention_days": 5})
    flags = await gate.tenant_gate_flags(mongo_db, "t1")
    assert flags["logs"] == {"waiting": True, "reason": "shortened"}
    assert flags["agent_metrics"] == {"waiting": False, "reason": None}
    await seed_tenant(mongo_db, "t-new")                       # never seen after the confirmation: adopted
    assert all(not f["waiting"] for f in (await gate.tenant_gate_flags(mongo_db, "t-new")).values())


# --------------------------------------------------------------------------- migration 027

@pytest.mark.asyncio
async def test_migration_027_is_idempotent_and_creates_the_indexes(mongo_db):
    await migration.up(mongo_db)
    first = {c: set(await mongo_db[c].index_information()) for c in
             ("retention_gate", "retention_counts", "retention_job_runs")}
    await migration.up(mongo_db)
    second = {c: set(await mongo_db[c].index_information()) for c in first}
    assert first == second
    gate_info = await mongo_db.retention_gate.index_information()
    assert gate_info["retention_gate_tenant_type"]["unique"] is True
    assert gate_info["retention_gate_tenant_type"]["key"] == [("tenantId", 1), ("type", 1)]
    counts_info = await mongo_db.retention_counts.index_information()
    assert counts_info["retention_counts_tenant_type"]["unique"] is True
    assert (await mongo_db.retention_job_runs.index_information())["retention_runs_started"]["key"] == \
        [("startedAt", -1)]
    assert hasattr(migration, "DESCRIPTION")
