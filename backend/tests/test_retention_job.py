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


def oid(days_ago, *, now=NOW, seconds=0):
    return ObjectId.from_datetime(now - timedelta(days=days_ago, seconds=seconds))


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
