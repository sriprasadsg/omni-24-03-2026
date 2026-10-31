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


# ------------------------------------------------------------------ Task 3: the review in detail

async def waiting_world(db):
    """Four tenants counted once: t3 has 5 old agent metrics, t1 and t2 have 3, t4 has 1."""
    await seed_tenant(db, "t3")
    await seed_tenant(db, "t4")
    for tenant, old in (("t1", 3), ("t2", 3), ("t3", 5), ("t4", 1)):
        await seed_old_metrics(db, tenant, old=old, new=1)
    await job.run_all(db, trigger="scheduled")


async def test_paging_is_25_per_page_with_a_token_that_covers_every_row(rapi):
    await waiting_world(rapi.db)
    first = (await rapi.call("GET", REVIEW, role="super_admin")).json()
    assert first["total"] == 32 and len(first["items"]) == 25 and first["nextOffset"] == 25
    second = (await rapi.call("GET", REVIEW + "?offset=25", role="super_admin")).json()
    assert len(second["items"]) == 7 and second["nextOffset"] is None and second["total"] == 32
    assert first["reviewToken"] == second["reviewToken"]
    ids = [(i["tenantId"], i["type"]) for i in first["items"] + second["items"]]
    assert len(ids) == len(set(ids)) == 32
    small = (await rapi.call("GET", REVIEW + "?limit=10&offset=30", role="super_admin")).json()
    assert len(small["items"]) == 2 and small["nextOffset"] is None


async def test_paging_arguments_are_validated(rapi):
    for query in ("?offset=-1", "?limit=0", "?limit=101", "?offset=x"):
        assert (await rapi.call("GET", REVIEW + query, role="super_admin")).status_code == 422, query


async def test_rows_are_ordered_by_count_then_tenant_name(rapi):
    await waiting_world(rapi.db)
    items = (await rapi.call("GET", REVIEW, role="super_admin")).json()["items"]
    top = [(i["tenantName"], i["type"], i["count"]) for i in items[:4]]
    assert top == [("T3", "agent_metrics", 5), ("T1", "agent_metrics", 3), ("T2", "agent_metrics", 3),
                   ("T4", "agent_metrics", 1)]
    counts = [i["count"] for i in items]
    assert counts == sorted(counts, reverse=True)


async def test_an_uncountable_row_is_listed_counted_in_the_totals_and_left_out_of_confirm(rapi):
    db = rapi.db
    await seed_old_metrics(db, "t1")
    await job.run_all(db, trigger="scheduled")
    await db.retention_counts.update_one({"tenantId": "t1", "type": "logs"},
                                         {"$set": {"count": None, "error": "ExecutionTimeout: too slow"}})
    body = (await rapi.call("GET", REVIEW, role="super_admin")).json()
    bad = [i for i in body["items"] if i["tenantId"] == "t1" and i["type"] == "logs"][0]
    assert bad["count"] is None and bad["countError"]
    assert body["totals"]["uncountable"] == 1 and body["totals"]["rows"] == 16
    res = await rapi.call("POST", CONFIRM, role="super_admin", json={"reviewToken": body["reviewToken"]})
    assert res.status_code == 200 and res.json()["confirmed"]["rows"] == 15 and res.json()["confirmed"]["records"] == 3
    gate_row = await db.retention_gate.find_one({"tenantId": "t1", "type": "logs"})
    assert gate_row["confirmedDays"] is None                               # still waiting


async def test_before_the_first_count_nothing_is_listed_and_not_counted_yet_is_true(rapi):
    body = (await rapi.call("GET", REVIEW, role="super_admin")).json()
    assert body["notCountedYet"] is True and body["items"] == [] and body["total"] == 0
    assert body["mode"] == "counting_only" and body["lastRun"] is None and body["countedAt"] is None
    assert body["nextRun"] and datetime.fromisoformat(body["nextRun"]).hour == 2
    assert body["totals"] == {"records": 0, "tenants": 0, "rows": 0, "uncountable": 0}


async def test_after_a_run_the_review_reports_the_last_run_and_when_it_counted(rapi):
    await seed_old_metrics(rapi.db, "t1")
    await job.run_all(rapi.db, trigger="scheduled")
    body = (await rapi.call("GET", REVIEW, role="super_admin")).json()
    assert body["notCountedYet"] is False and body["countedAt"]
    last = body["lastRun"]
    assert (last["trigger"], last["counted"], last["deleted"], last["tenants"]) == ("scheduled", 3, 0, 2)
    assert last["error"] is None and last["stoppedEarly"] is False and last["at"]


async def test_a_failed_last_run_reports_its_error(rapi, monkeypatch):
    async def broken(*args, **kwargs):
        raise RuntimeError("disk full")

    await seed_old_metrics(rapi.db, "t1")
    await job.run_all(rapi.db, trigger="scheduled")
    res = await rapi.call("GET", REVIEW, role="super_admin")
    token = res.json()["reviewToken"]
    await rapi.call("POST", CONFIRM, role="super_admin", json={"reviewToken": token})
    monkeypatch.setattr(job, "delete_type", broken)
    await job.run_all(rapi.db, trigger="scheduled")
    last = (await rapi.call("GET", REVIEW, role="super_admin")).json()["lastRun"]
    assert last["error"] and "disk full" in last["error"]


async def test_once_everything_is_confirmed_the_mode_is_deleting_nightly(rapi):
    await seed_old_metrics(rapi.db, "t1")
    await job.run_all(rapi.db, trigger="scheduled")
    token = (await rapi.call("GET", REVIEW, role="super_admin")).json()["reviewToken"]
    assert (await rapi.call("POST", CONFIRM, role="super_admin", json={"reviewToken": token})).status_code == 200
    body = (await rapi.call("GET", REVIEW, role="super_admin")).json()
    assert body["mode"] == "deleting_nightly" and body["items"] == [] and body["notCountedYet"] is False


async def test_an_unfinished_run_means_mode_running_and_confirm_answers_409(rapi):
    await seed_old_metrics(rapi.db, "t1")
    await job.run_all(rapi.db, trigger="scheduled")
    token = (await rapi.call("GET", REVIEW, role="super_admin")).json()["reviewToken"]
    await rapi.db.retention_job_runs.insert_one({"startedAt": datetime.now(timezone.utc), "trigger": "scheduled"})
    assert (await rapi.call("GET", REVIEW, role="super_admin")).json()["mode"] == "running"
    res = await rapi.call("POST", CONFIRM, role="super_admin", json={"reviewToken": token})
    assert res.status_code == 409 and "in progress" in res.json()["detail"]
    assert await rapi.db.retention_gate.count_documents({"confirmedDays": {"$ne": None}}) == 0


async def test_a_held_run_lock_means_mode_running_too(rapi):
    await rapi.db["_distributed_locks"].insert_one(
        {"_id": job.LOCK_NAME, "token": "other", "expiresAt": datetime.now(timezone.utc) + timedelta(minutes=5)})
    assert (await rapi.call("GET", REVIEW, role="super_admin")).json()["mode"] == "running"
    await rapi.db["_distributed_locks"].update_one(
        {"_id": job.LOCK_NAME}, {"$set": {"expiresAt": datetime.now(timezone.utc) - timedelta(minutes=5)}})
    assert (await rapi.call("GET", REVIEW, role="super_admin")).json()["mode"] == "counting_only"


async def test_a_token_from_before_a_recount_answers_409_and_confirms_nothing(rapi):
    db = rapi.db
    await seed_old_metrics(db, "t1")
    await job.run_all(db, trigger="scheduled")
    stale = (await rapi.call("GET", REVIEW, role="super_admin")).json()["reviewToken"]
    await seed_old_metrics(db, "t1", old=2, new=0)                         # the counts change
    await job.run_all(db, trigger="scheduled")
    res = await rapi.call("POST", CONFIRM, role="super_admin", json={"reviewToken": stale})
    assert res.status_code == 409 and "counts changed" in res.json()["detail"]
    assert await db.retention_gate.count_documents({"confirmedDays": {"$ne": None}}) == 0
    assert await db.retention_gate_global.count_documents({}) == 0
    fresh = (await rapi.call("GET", REVIEW, role="super_admin")).json()["reviewToken"]
    assert (await rapi.call("POST", CONFIRM, role="super_admin", json={"reviewToken": fresh})).status_code == 200


async def test_manual_run_before_the_first_nightly_run_then_confirm_is_refused(rapi):
    db = rapi.db
    await seed_old_metrics(db, "t1")
    await job.run_manual(db, "t1")

    body = (await rapi.call("GET", REVIEW, role="super_admin")).json()
    assert body["incomplete"] == {"reason": "not_reached", "tenants": 1}
    res = await rapi.call("POST", CONFIRM, role="super_admin", json={"reviewToken": body["reviewToken"]})
    assert res.status_code == 409 and res.json()["detail"] == review_ep.REVIEW_INCOMPLETE
    assert await db.retention_gate.count_documents({"confirmedDays": {"$ne": None}}) == 0
    assert await db.retention_gate_global.count_documents({}) == 0

    await job.run_all(db, trigger="scheduled")
    fresh = (await rapi.call("GET", REVIEW, role="super_admin")).json()
    assert fresh["incomplete"] is None
    assert (await rapi.call("POST", CONFIRM, role="super_admin",
                            json={"reviewToken": fresh["reviewToken"]})).status_code == 200


async def test_review_reports_incomplete_null_after_a_clean_run(rapi):
    await seed_old_metrics(rapi.db, "t1")
    await job.run_all(rapi.db, trigger="scheduled")
    body = (await rapi.call("GET", REVIEW, role="super_admin")).json()
    assert "incomplete" in body and body["incomplete"] is None


async def test_confirm_with_no_countable_rows_answers_422(rapi):
    db = rapi.db
    body = (await rapi.call("GET", REVIEW, role="super_admin")).json()          # nothing counted yet
    res = await rapi.call("POST", CONFIRM, role="super_admin", json={"reviewToken": body["reviewToken"]})
    assert res.status_code == 422
    await seed_old_metrics(db, "t1")
    await job.run_all(db, trigger="scheduled")
    await db.retention_counts.update_many({}, {"$set": {"count": None, "error": "failed"}})
    token = (await rapi.call("GET", REVIEW, role="super_admin")).json()["reviewToken"]
    assert (await rapi.call("POST", CONFIRM, role="super_admin", json={"reviewToken": token})).status_code == 422
    assert await db.retention_gate_global.count_documents({}) == 0


async def test_confirm_validates_its_body(rapi):
    assert (await rapi.call("POST", CONFIRM, role="super_admin", json={})).status_code == 422
    assert (await rapi.call("POST", CONFIRM, role="super_admin", json={"reviewToken": ""})).status_code == 422
    assert (await rapi.call("POST", CONFIRM, role="super_admin", json={"reviewToken": "x" * 129})).status_code == 422


@pytest.mark.parametrize("role", ["tenant_admin", "viewer", "platform_support"])
async def test_only_the_super_admin_may_review_or_confirm(rapi, role):
    assert (await rapi.call("GET", REVIEW, role=role)).status_code == 403
    assert (await rapi.call("POST", CONFIRM, role=role, json={"reviewToken": "abc"})).status_code == 403


async def test_an_api_key_cannot_review_or_confirm(rapi):
    assert (await rapi.call("GET", REVIEW, role="super_admin", auth="api_key", scopes=["*"])).status_code == 403
    assert (await rapi.call("POST", CONFIRM, role="super_admin", auth="api_key", scopes=["*"],
                            json={"reviewToken": "abc"})).status_code == 403
