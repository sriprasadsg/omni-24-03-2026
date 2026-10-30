"""Super Admin retention review and confirm (Phase 82, plan 82-10, HEAL-06, HEAL-07, D-18, D-20).

GET /api/platform/autonomous-ops/retention/review lists what the first nightly run counted and
POST .../confirm confirms every countable row at once with the review token. Real Mongo through the
throwaway database of tests/_mongo_test_db.py (set MONGO_TEST_URL to a private mongod).
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-platform-retention-review")

import autonomous_ops_retention_endpoints as review_ep
import retention_gate as gate
import retention_job as job
from tests._autonomous_ops_http import api  # noqa: F401  (fixture)
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_tenant

REVIEW = "/api/platform/autonomous-ops/retention/review"
CONFIRM = "/api/platform/autonomous-ops/retention/confirm"
PLATFORM_LIST = "/api/platform/autonomous-ops/actions?bucket=platform_health"


def oid(days_ago, seconds=0, *, now=None):
    """A unique ObjectId created ``days_ago`` days (plus ``seconds``) before ``now``."""
    now = now or datetime.now(timezone.utc)
    stamp = ObjectId.from_datetime(now - timedelta(days=days_ago, seconds=seconds)).binary[:4]
    return ObjectId(stamp + os.urandom(8))


async def seed_old_metrics(db, tenant_id, old=3, new=2, collection="agent_metrics"):
    docs = [{"_id": oid(40, seconds=i), "tenant_id": tenant_id, "n": i} for i in range(old)]
    docs += [{"_id": oid(5, seconds=i), "tenant_id": tenant_id, "n": 100 + i} for i in range(new)]
    if docs:
        await db[collection].insert_many(docs)


@pytest.fixture
async def rapi(api, monkeypatch):  # noqa: F811
    """The Phase 81 platform app plus the retention review router."""
    monkeypatch.setattr(review_ep, "get_database", lambda: api.db)
    api.app.include_router(review_ep.router)
    return api


async def health_rows(api):
    res = await api.call("GET", PLATFORM_LIST, role="super_admin")
    assert res.status_code == 200
    return res.json()["items"]


# ------------------------------------------------------------------ Task 1: the tracer

async def test_review_confirm_activity_and_the_next_run_deletes(rapi):
    db = rapi.db
    await seed_old_metrics(db, "t1")

    first = await job.run_all(db, trigger="scheduled")
    assert first["deleted"] == 0 and first["counted"] == 3

    # the counting run wrote one retention_run row with mode counted
    rows = await health_rows(rapi)
    assert [r["actionLabel"] for r in rows] == ["Retention run"]
    assert rows[0]["resultText"] == "Counted 3 records across 2 organizations. Deleted nothing."
    assert rows[0]["healthChip"] == "healthy"

    # the review lists the counted row and its token
    res = await rapi.call("GET", REVIEW, role="super_admin")
    assert res.status_code == 200
    body = res.json()
    assert body["mode"] == "counting_only"
    metrics = [i for i in body["items"] if i["type"] == "agent_metrics" and i["tenantId"] == "t1"]
    assert len(metrics) == 1
    item = metrics[0]
    assert (item["tenantId"], item["tenantName"], item["label"], item["days"], item["count"], item["reason"]) \
        == ("t1", "T1", "Agent metrics", 30, 3, "first_run")
    assert body["items"][0]["type"] == "agent_metrics" and body["items"][0]["tenantId"] == "t1"   # largest first
    assert body["totals"]["records"] == 3 and body["totals"]["tenants"] == 2     # every countable row counts
    assert body["totals"]["uncountable"] == 0
    token = body["reviewToken"]
    assert token

    # confirming answers the totals and writes one retention_confirmed row naming the person
    res = await rapi.call("POST", CONFIRM, role="super_admin", username="root@example.test",
                          json={"reviewToken": token})
    assert res.status_code == 200
    confirmed = res.json()["confirmed"]
    assert confirmed["records"] == 3 and confirmed["tenants"] == 2 and confirmed["rows"] == len(body["items"])
    rows = await health_rows(rapi)
    confirmed_rows = [r for r in rows if r["actionLabel"] == "Retention confirmed"]
    assert len(confirmed_rows) == 1
    assert "root@example.test" in confirmed_rows[0]["reasonText"]
    assert confirmed_rows[0]["source"] == "Super Admin"

    # nothing was deleted by the confirmation itself; the next run deletes and writes mode deleted
    assert await db.agent_metrics.count_documents({}) == 5
    second = await job.run_all(db, trigger="scheduled")
    assert second["deleted"] == 3
    assert await db.agent_metrics.count_documents({}) == 2
    runs = [r for r in await health_rows(rapi) if r["actionLabel"] == "Retention run"]
    assert len(runs) == 2
    assert any(r["resultText"] == "Deleted 3 records across 2 organizations." for r in runs)


# ------------------------------------------------------------------ the scheduled run's Activity row

async def test_a_scheduled_run_writes_one_row_and_a_manual_run_writes_none(rapi):
    db = rapi.db
    await job.run_manual(db, "t1")
    assert await health_rows(rapi) == []
    await job.run_all(db, trigger="scheduled")
    rows = await health_rows(rapi)
    assert len(rows) == 1
    stored = await db.autonomy_actions.find_one({"healthEvent": "retention_run"})
    assert stored["healthParams"]["mode"] == "counted"
    assert stored["healthParams"]["ok"] is True and stored["healthParams"].get("error") is None
    assert stored["healthParams"]["tenants"] == 2          # t1 and t2 from the api fixture


async def test_a_ledger_failure_never_fails_the_run(rapi, monkeypatch):
    from autonomous_ops import ledger

    async def boom(*args, **kwargs):
        raise ledger.LedgerUnavailable("down")

    monkeypatch.setattr(ledger, "record_platform_health", boom)
    summary = await job.run_all(rapi.db, trigger="scheduled")
    assert summary["tenants"] == 2
    assert await rapi.db.retention_job_runs.count_documents({}) == 1


async def test_a_run_that_deleted_something_records_mode_deleted_with_the_deleted_total(rapi):
    db = rapi.db
    await seed_old_metrics(db, "t1")
    await job.run_all(db, trigger="scheduled")
    res = await rapi.call("GET", REVIEW, role="super_admin")
    assert (await rapi.call("POST", CONFIRM, role="super_admin", json={"reviewToken": res.json()["reviewToken"]})
            ).status_code == 200
    await job.run_all(db, trigger="scheduled")
    stored = [d async for d in db.autonomy_actions.find({"healthEvent": "retention_run"}).sort("createdAt", 1)]
    assert [d["healthParams"]["mode"] for d in stored] == ["counted", "deleted"]
    assert stored[1]["healthParams"]["records"] == 3
