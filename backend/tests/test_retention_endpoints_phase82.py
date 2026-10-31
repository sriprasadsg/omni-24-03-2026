"""Tenant retention routes after Phase 82 (plan 82-10, HEAL-06, D-16, D-17, D-19, D-25, D-26).

The manual run honours the same count-only gate as the nightly job, never touches audit logs, names the
next run, and the policy list tells the tenant which of its own data types wait for a confirmation.
Real Mongo through the throwaway database of tests/_mongo_test_db.py (set MONGO_TEST_URL to a private
mongod); the routes run behind the tenant-isolating wrapper exactly as in production.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from bson import ObjectId
from fastapi import FastAPI

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-retention-endpoints")

import retention_endpoints as ep
import retention_gate as gate
import retention_job as job
import tenant_context
from auth_types import TokenData
from auth_utils import require_auth
from database import TenantIsolatedDatabase
from retention_service import RetentionService
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.autonomy_support import seed_tenant

BUSY = "A retention run is in progress. Try again when it finishes."
AUDIT_NOTE = "Audit logs are kept by the audit ledger's own schedule, not by this cleanup."


def oid(days_ago, seconds=0):
    stamp = ObjectId.from_datetime(datetime.now(timezone.utc) - timedelta(days=days_ago, seconds=seconds)).binary[:4]
    return ObjectId(stamp + os.urandom(8))


def iso(days_ago):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


class Client:
    """The retention router behind the tenant wrapper; the caller is chosen per request."""

    def __init__(self, db, monkeypatch):
        self.db = db
        self.wrapped = TenantIsolatedDatabase(db)
        monkeypatch.setattr(ep, "get_database", lambda: self.wrapped)
        self.user = None
        self.app = FastAPI()
        self.app.include_router(ep.router)

        async def _auth():
            tenant_context.set_tenant_id(self.user.tenant_id)      # what the auth middleware does per request
            return self.user

        self.app.dependency_overrides[require_auth] = _auth

    async def call(self, method, path, *, tenant="t1", role="tenant_admin", json=None):
        self.user = TokenData(username=f"{role}@{tenant}.test", role=role, tenant_id=tenant)
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, path, json=json)


@pytest.fixture
async def client(mongo_db, monkeypatch):  # noqa: F811
    await seed_tenant(mongo_db, "t1")
    await seed_tenant(mongo_db, "t2")
    # the periods these tests read and write are stored explicitly, so they do not depend on which
    # defaults the route seeds
    await mongo_db.retention_policies.insert_many(
        [{"tenantId": tenant, "collection": name, "retention_days": days}
         for tenant in ("t1", "t2") for name, days in (("agent_metrics", 30), ("logs", 30), ("notifications", 30))])
    return Client(mongo_db, monkeypatch)


async def seed_data(db, tenant):
    """Old and new agent metrics, notifications and audit logs for one tenant."""
    await db.agent_metrics.insert_many(
        [{"_id": oid(40, i), "tenant_id": tenant} for i in range(3)] + [{"_id": oid(2, i), "tenant_id": tenant} for i in range(2)])
    await db.notifications.insert_many(
        [{"tenantId": tenant, "sent_at": iso(40), "n": i} for i in range(4)] + [{"tenantId": tenant, "sent_at": iso(1)}])
    await db.audit_logs.insert_many([{"tenantId": tenant, "timestamp": iso(400), "n": i} for i in range(5)])


async def confirm_everything(db):
    rows = await gate.review_rows(db)
    return await gate.confirm(db, gate.review_token(rows), "root@platform.test", datetime.now(timezone.utc))


def by_type(res):
    return {t["type"]: t for t in res.json()["types"]}


# ------------------------------------------------------------------ manual run: the gate (D-26, PROH-82-10)

async def test_manual_run_counts_waiting_types_and_deletes_nothing(client):
    db = client.db
    await seed_data(db, "t1")
    res = await client.call("POST", "/api/retention/run")
    assert res.status_code == 200 and res.json()["status"] == "completed"
    types = by_type(res)
    assert (types["agent_metrics"]["state"], types["agent_metrics"]["count"]) == ("counted", 3)
    assert (types["notifications"]["state"], types["notifications"]["count"]) == ("counted", 4)
    assert set(types) == set(gate.TYPE_IDS)
    assert await db.agent_metrics.count_documents({}) == 5
    assert await db.notifications.count_documents({}) == 5
    assert await db.audit_logs.count_documents({"tenantId": "t1"}) == 5       # D-16: never deleted
    run = await db.retention_runs.find_one({})
    assert run["tenantId"] == "t1" and run["result"]["agent_metrics_counted"] == 3


async def test_manual_run_deletes_only_the_confirmed_types_of_the_callers_tenant(client):
    db = client.db
    await seed_data(db, "t1")
    await seed_data(db, "t2")
    await job.run_all(db, trigger="scheduled")                  # counts both tenants
    await confirm_everything(db)

    res = await client.call("POST", "/api/retention/run", tenant="t1")
    assert res.status_code == 200
    types = by_type(res)
    assert (types["agent_metrics"]["state"], types["agent_metrics"]["deleted"]) == ("deleted", 3)
    assert (types["notifications"]["state"], types["notifications"]["deleted"]) == ("deleted", 4)
    assert res.json()["result"]["agent_metrics_deleted"] == 3
    assert await db.agent_metrics.count_documents({"tenant_id": "t1"}) == 2
    assert await db.agent_metrics.count_documents({"tenant_id": "t2"}) == 5       # untouched
    assert await db.notifications.count_documents({"tenantId": "t2"}) == 5
    assert await db.audit_logs.count_documents({"n": {"$exists": True}}) == 10    # both tenants, nothing removed


async def test_a_shortened_period_goes_back_to_counting_for_the_manual_run(client):
    db = client.db
    await seed_data(db, "t1")
    await job.run_all(db, trigger="scheduled")
    await confirm_everything(db)
    saved = await client.call("POST", "/api/retention/policies/agent_metrics", json={"retention_days": 20})
    assert saved.status_code == 200 and saved.json()["countOnlyUntilConfirmed"] is True
    res = await client.call("POST", "/api/retention/run")
    types = by_type(res)
    assert types["agent_metrics"]["state"] == "counted"
    assert types["notifications"]["state"] == "deleted"
    assert await db.agent_metrics.count_documents({"tenant_id": "t1"}) == 5


async def test_manual_run_for_an_unreached_tenant_after_the_confirmation_only_counts(client):
    """T-82-36: t2 was never reached by the first pass; a confirmation then exists; the manual run counts."""
    db = client.db
    await seed_data(db, "t1")
    await seed_data(db, "t2")
    await job.run_tenant(db, "t1", now=datetime.now(timezone.utc))
    await db[gate.GATE_GLOBAL].update_one(
        {"_id": gate.GLOBAL_ID}, {"$setOnInsert": {"confirmedAt": datetime.now(timezone.utc) - timedelta(days=1)}},
        upsert=True)
    assert await db.retention_gate.count_documents({"tenantId": "t2"}) == 0

    res = await client.call("POST", "/api/retention/run", tenant="t2")

    assert res.status_code == 200
    types = by_type(res)
    assert (types["agent_metrics"]["state"], types["agent_metrics"]["count"]) == ("counted", 3)
    assert await db.agent_metrics.count_documents({"tenant_id": "t2"}) == 5
    assert await db.notifications.count_documents({"tenantId": "t2"}) == 5


async def test_manual_run_answers_409_and_records_nothing_while_a_run_is_in_progress(client):
    db = client.db
    await seed_data(db, "t1")
    await db["_distributed_locks"].insert_one(
        {"_id": job.LOCK_NAME, "token": "other", "expiresAt": datetime.now(timezone.utc) + timedelta(minutes=5)})
    res = await client.call("POST", "/api/retention/run")
    assert res.status_code == 409 and res.json()["detail"] == BUSY
    assert await db.retention_runs.count_documents({}) == 0
    assert await db.retention_job_runs.count_documents({}) == 0
    assert await db.agent_metrics.count_documents({}) == 5


async def test_manual_run_without_a_tenant_is_refused_before_anything_runs(client, monkeypatch):
    async def must_not_run(*args, **kwargs):
        raise AssertionError("run_manual must not be called without a tenant")

    monkeypatch.setattr(job, "run_manual", must_not_run)
    self_user = TokenData(username="x@y.test", role="tenant_admin", tenant_id=None)
    client.user = self_user
    client.app.dependency_overrides[require_auth] = lambda: self_user
    transport = httpx.ASGITransport(app=client.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
        res = await http.post("/api/retention/run")
    assert res.status_code == 400
    assert await client.db.retention_runs.count_documents({}) == 0


async def test_manual_run_needs_a_tenant_admin(client):
    res = await client.call("POST", "/api/retention/run", role="viewer")
    assert res.status_code == 403


async def test_manual_run_never_calls_the_old_cleanup(client, monkeypatch):
    async def boom(self, *args, **kwargs):
        raise AssertionError("RetentionService.run_cleanup must not be on the manual path")

    monkeypatch.setattr(RetentionService, "run_cleanup", boom)
    assert (await client.call("POST", "/api/retention/run")).status_code == 200


def test_the_service_no_longer_deletes_audit_logs():
    assert not hasattr(RetentionService, "cleanup_audit_logs")


# ------------------------------------------------------------------ stats (D-17)

async def test_stats_names_the_next_nightly_run(client):
    res = await client.call("GET", "/api/retention/stats")
    assert res.status_code == 200
    value = res.json()["next_scheduled"]
    nxt = datetime.fromisoformat(value)
    assert nxt.hour == 2 and nxt.minute == 0 and nxt.tzinfo is not None
    assert nxt > datetime.now(timezone.utc)
    assert nxt - datetime.now(timezone.utc) <= timedelta(days=1, minutes=1)


# ------------------------------------------------------------------ policies (D-19, D-25)

async def test_policies_carry_the_gate_flags_of_the_callers_own_tenant_only(client):
    db = client.db
    await job.run_all(db, trigger="scheduled")
    await confirm_everything(db)                              # both tenants confirmed
    await db.retention_gate.update_one({"tenantId": "t1", "type": "logs"}, {"$set": {"confirmedDays": 90}})
    await client.call("POST", "/api/retention/policies/logs", json={"retention_days": 10})     # t1 shortens logs

    mine = await client.call("GET", "/api/retention/policies", tenant="t1")
    flags = {p["collection"]: p["gate"] for p in mine.json()["policies"]}
    assert flags["logs"] == {"waiting": True, "reason": "shortened"}
    assert flags["agent_metrics"] == {"waiting": False, "reason": None}
    assert flags["alerts"] == {"waiting": False, "reason": None}       # not a data type of the job

    other = await client.call("GET", "/api/retention/policies", tenant="t2")
    assert {p["collection"]: p["gate"] for p in other.json()["policies"]}["logs"] == {"waiting": False, "reason": None}
    assert "count" not in json.dumps(mine.json()).replace("countOnly", "")
    for policy in mine.json()["policies"] + other.json()["policies"]:
        assert set(policy["gate"]) == {"waiting", "reason"}


async def test_the_audit_logs_policy_is_marked_managed_and_not_editable(client):
    res = await client.call("GET", "/api/retention/policies")
    policies = {p["collection"]: p for p in res.json()["policies"]}
    assert policies["audit_logs"]["managedBy"] == "audit_ledger" and policies["audit_logs"]["editable"] is False
    assert policies["metrics"]["editable"] is True and "managedBy" not in policies["metrics"]


async def test_writing_the_audit_logs_policy_is_refused_with_409(client):
    res = await client.call("POST", "/api/retention/policies/audit_logs", json={"retention_days": 30})
    assert res.status_code == 409 and res.json()["detail"] == AUDIT_NOTE
    stored = await client.db.retention_policies.find_one({"collection": "audit_logs", "tenantId": "t1"})
    assert stored is None or stored["retention_days"] == 90          # nothing was written


async def test_a_shorter_period_is_count_only_until_confirmed_and_a_longer_one_is_not(client):
    db = client.db
    await job.run_all(db, trigger="scheduled")
    await confirm_everything(db)                                      # agent_metrics confirmed at 30
    shorter = await client.call("POST", "/api/retention/policies/agent_metrics", json={"retention_days": 20})
    assert shorter.status_code == 200 and shorter.json()["countOnlyUntilConfirmed"] is True
    longer = await client.call("POST", "/api/retention/policies/agent_metrics", json={"retention_days": 60})
    assert longer.status_code == 200 and longer.json()["countOnlyUntilConfirmed"] is False
    assert longer.json()["retention_days"] == 60 and longer.json()["updated"] is True


# ------------------------------------------------------------------ the policy writer and the job's reader agree

async def test_a_period_saved_through_the_route_is_the_period_the_job_reads_for_that_tenant_only(client):
    res = await client.call("POST", "/api/retention/policies/agent_metrics", json={"retention_days": 45}, tenant="t1")
    assert res.status_code == 200
    assert (await gate.load_policy_days(client.db, "t1"))["agent_metrics"] == 45
    assert (await gate.load_policy_days(client.db, "t2"))["agent_metrics"] == 30        # t2 keeps its own
