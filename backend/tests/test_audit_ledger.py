"""Spec C5: one audit writer, an atomic per-tenant hash chain, a middleware that audits
every mutating API call, explicit login events, scoped reads, spooling and retention.
Real MongoDB (skips without one); requests go through real ASGI middleware via httpx.

Value: protects=each mutating call yields exactly one entry with the right actor, tenant,
route-template action, catalogue and outcome; body values never reach the log; concurrent
writers get contiguous seq numbers and a chain verify accepts (and catches tampering); a
failed write is spooled and replayed; a failed login records email + IP but no password;
tenant admins read only their own tenant; retention purges past a checkpoint without
breaking verification; the middleware adds <=10 ms p95; fails_when=entries are missing,
duplicated, unchained or forked, values leak, or another tenant's entries are readable;
no_claim=uvicorn's send-before-write timing (httpx waits for the app to finish, so the
benchmark includes the write) and multi-process writers (one event loop).
"""
import asyncio
import json
import os
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI, HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import audit_endpoints
import audit_ledger
from audit_middleware import AuditMiddleware
from auth_types import TokenData
from authentication_service import create_access_token
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tenant_middleware import TenantMiddleware

SECRET = "S3cret-Value-Never-Logged!"
_MANIFEST = json.load(open(os.path.join(os.path.dirname(__file__), "..", "..", "shared", "catalogue-access.json")))
# One real catalogue route per catalogue group: {view: route prefix}.
GROUP_PATHS = {}
for _group in _MANIFEST["groups"]:
    _cat = next((c for c in _MANIFEST["catalogues"] if c["group"] == _group["id"] and c.get("routes")), None)
    if _cat:
        GROUP_PATHS[_cat["view"]] = _cat["routes"][0].rstrip("/")


@pytest.fixture
def live_db(mongo_db, monkeypatch):
    import database
    monkeypatch.setattr(database.mongodb, "db", mongo_db)
    return mongo_db


def _token(email="alice@a.example", role="Tenant Admin", tenant="tenant-a", **extra):
    return create_access_token({"sub": email, "role": role, "tenant_id": tenant, "mfa_verified": True, **extra},
                               expires_delta=timedelta(minutes=5))


def _app(audited=True):
    app = FastAPI()

    async def ok(item_id: str):
        return {"ok": item_id}

    for prefix in GROUP_PATHS.values():
        app.add_api_route(f"{prefix}/{{item_id}}", ok, methods=["PATCH"])

    @app.post("/api/users")
    async def create_user(body: dict):
        return {"id": "u1"}

    @app.delete("/api/tenants/{tenant_id}")
    async def forbidden(tenant_id: str):
        raise HTTPException(status_code=403, detail="no")

    @app.post("/api/agents/{agent_id}/heartbeat")
    async def heartbeat(agent_id: str):
        return {"success": True}

    @app.post("/api/agents/register")
    async def register(body: dict):
        return {"agentId": "a1"}

    if audited:
        app.add_middleware(AuditMiddleware)
    app.add_middleware(TenantMiddleware)
    return app


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("198.51.100.9", 4444)),
                             base_url="http://test")


async def _entries(db, **query):
    return await db.audit_logs.find(query, {"_id": 0}).sort("seq", 1).to_list(1000)


async def test_one_entry_per_mutating_call_across_the_catalogue_groups(live_db):
    """AC1 + exclusions. protects=one PATCH per catalogue group -> exactly one entry each with
    actor, tenant, route-template action, catalogue and outcome; a 403 is 'denied'; agent
    data-plane calls are not recorded but enrollment is."""
    headers = {"Authorization": f"Bearer {_token()}", "User-Agent": "pytest"}
    async with _client(_app()) as c:
        for prefix in GROUP_PATHS.values():
            assert (await c.patch(f"{prefix}/thing-1", json={"name": "x"}, headers=headers)).status_code == 200
        assert (await c.delete("/api/tenants/tenant-b", headers=headers)).status_code == 403
        agent = {"Authorization": f"Bearer {_token('agent-1', role='agent', typ='agent')}"}
        await c.post("/api/agents/agent-1/heartbeat", json={}, headers=agent)
        await c.post("/api/agents/agent-1/heartbeat", json={}, headers={"X-Tenant-Key": "reg_x"})
        await c.post("/api/agents/register", json={"registrationKey": "reg_x", "hostname": "h"})
    assert len(GROUP_PATHS) == len(_MANIFEST["groups"]) == 8
    entries = await _entries(live_db, source="request")
    by_action = {e["action"]: e for e in entries}
    for view, prefix in GROUP_PATHS.items():
        e = by_action[f"PATCH {prefix}/{{item_id}}"]
        assert (e["tenantId"], e["actor"]["email"], e["actor"]["role"], e["outcome"]) == \
            ("tenant-a", "alice@a.example", "Tenant Admin", "success")
        assert e["resourceId"] == "thing-1" and e["bodyKeys"] == ["name"] and e["ip"] == "198.51.100.9"
        assert e["catalogue"] == view and e["statusCode"] == 200 and e["userAgent"] == "pytest"
    denied = by_action["DELETE /api/tenants/{tenant_id}"]
    assert denied["outcome"] == "denied" and denied["statusCode"] == 403
    assert "POST /api/agents/{agent_id}/heartbeat" not in by_action
    assert "POST /api/agents/register" in by_action
    assert len(entries) == len(GROUP_PATHS) + 2
    assert (await audit_ledger.verify("tenant-a", db=live_db))["valid"]


async def test_body_values_never_reach_the_log(live_db):
    """AC4. protects=POST /api/users with a password records the key, never the value."""
    async with _client(_app()) as c:
        await c.post("/api/users", json={"email": "bob@a.example", "password": SECRET},
                     headers={"Authorization": f"Bearer {_token()}"})
    (entry,) = await _entries(live_db, action="POST /api/users")
    assert entry["bodyKeys"] == ["email", "password"]
    assert SECRET not in json.dumps(entry, default=str) and "bob@a.example" not in json.dumps(entry, default=str)


async def test_failed_login_records_email_and_ip_but_not_the_password(live_db):
    """AC5. protects=the real /api/auth/login route on a bad password records login.failure with
    the email tried and the IP, and no password; the raw request is not double-logged."""
    import authentication_endpoints
    from rate_limiter import limiter
    app = FastAPI()
    app.include_router(authentication_endpoints.router)
    app.add_middleware(AuditMiddleware)
    app.add_middleware(TenantMiddleware)
    from database import TenantIsolatedDatabase
    # Pin the handler's own get_database: other test modules can leave it bound to a
    # client from a closed event loop.
    with patch.object(limiter, "enabled", False), \
            patch.object(authentication_endpoints, "get_database", return_value=TenantIsolatedDatabase(live_db)):
        async with _client(app) as c:
            resp = await c.post("/api/auth/login", json={"email": "mallory@a.example", "password": SECRET})
    assert resp.status_code == 401
    entries = await _entries(live_db)
    assert [e["action"] for e in entries] == ["login.failure"]
    e = entries[0]
    assert e["email"] == "mallory@a.example" and e["ip"] == "198.51.100.9" and e["outcome"] == "denied"
    assert SECRET not in json.dumps(e, default=str)


async def test_concurrent_writers_get_a_contiguous_verifiable_chain(live_db):
    """AC3. protects=100 concurrent writes in one tenant -> seq 1..100 and verify passes; an
    edited entry is caught."""
    await asyncio.gather(*(audit_ledger.event("test.write", "tenant-a", db=live_db, n=i) for i in range(100)))
    entries = await _entries(live_db, tenantId="tenant-a")
    assert [e["seq"] for e in entries] == list(range(1, 101))
    report = await audit_ledger.verify("tenant-a", db=live_db)
    assert report["valid"] and report["total_records"] == 100
    await live_db.audit_logs.update_one({"tenantId": "tenant-a", "seq": 40}, {"$set": {"action": "edited"}})
    broken = await audit_ledger.verify("tenant-a", db=live_db)
    assert not broken["valid"] and broken["broken_links"][0]["seq"] == 40


async def test_a_failed_write_is_spooled_then_replayed(live_db, tmp_path, monkeypatch):
    """AC7. protects=an insert failure leaves the caller unharmed, spools the entry, and replay
    writes it so the chain verifies; fails_when=the entry is lost or the request raises."""
    monkeypatch.setenv("AUDIT_SPOOL_PATH", str(tmp_path / "spool.ndjson"))
    real_insert = live_db.audit_logs.insert_one
    with patch.object(type(live_db.audit_logs), "insert_one", AsyncMock(side_effect=RuntimeError("db down"))):
        entry = await audit_ledger.event("test.write", "tenant-a", db=live_db)
    assert (tmp_path / "spool.ndjson").read_text().count(entry["id"]) == 1
    assert await live_db.audit_logs.count_documents({}) == 0
    assert real_insert  # the patched method is restored below
    assert await audit_ledger.replay_spool(db=live_db) == 1
    assert await live_db.audit_logs.count_documents({"id": entry["id"]}) == 1
    assert not (tmp_path / "spool.ndjson").exists() or not (tmp_path / "spool.ndjson").read_text().strip()
    await audit_ledger.event("test.write", "tenant-a", db=live_db)
    assert (await audit_ledger.verify("tenant-a", db=live_db))["valid"]


async def test_retention_purge_keeps_the_chain_verifiable(live_db):
    """protects=entries past retention are purged with a checkpoint, verification starts there,
    and new entries continue the chain."""
    await live_db.tenants.insert_one({"id": "tenant-a", "auditRetentionDays": 30})
    for i in range(5):
        await audit_ledger.event("old.write", "tenant-a", db=live_db)
    await live_db.audit_logs.update_many({"seq": {"$lte": 3}},
                                         {"$set": {"timestamp": (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()}})
    # Back-dating changed hashed fields; re-hash those three so only retention is under test.
    for e in await _entries(live_db, tenantId="tenant-a"):
        prev = e["previousHash"] if e["seq"] == 1 else (await live_db.audit_logs.find_one({"seq": e["seq"] - 1}))["hash"]
        e["previousHash"] = prev
        e["hash"] = audit_ledger.entry_hash(e)
        await live_db.audit_logs.replace_one({"id": e["id"]}, e)
        await live_db.audit_chain_heads.update_one({"tenantId": "tenant-a"}, {"$set": {"seq": e["seq"], "hash": e["hash"]}})
    assert await audit_ledger.purge_expired(db=live_db) == 3
    await audit_ledger.event("new.write", "tenant-a", db=live_db)
    report = await audit_ledger.verify("tenant-a", db=live_db)
    assert report["valid"] and report["checkpoint"] == 3 and report["total_records"] == 3


async def test_tenant_admin_reads_only_its_own_tenant(live_db):
    """AC6. protects=a tenant admin of A gets only A's entries, even passing tenantId=B; a super
    admin can name B; the CSV export is itself audited."""
    await audit_ledger.event("a.write", "tenant-a", db=live_db)
    await audit_ledger.event("b.write", "tenant-b", db=live_db)
    admin_a = TokenData(username="alice@a.example", role="Tenant Admin", tenant_id="tenant-a", mfa_verified=True)
    root = TokenData(username="root@x", role="Super Admin", tenant_id="platform-admin", mfa_verified=True)
    import audit_service
    with patch.object(audit_service, "get_database", return_value=live_db):
        with patch.object(audit_endpoints, "get_tenant_id", return_value="tenant-a"):
            mine = await audit_endpoints.get_audit_logs(limit=100, skip=0, resourceType=None, resourceId=None, actor=None,
                                                        action=None, outcome=None, catalogue=None, from_=None, to=None,
                                                        tenantId="tenant-b", current_user=admin_a)
        with patch.object(audit_endpoints, "get_tenant_id", return_value="platform-admin"):
            theirs = await audit_endpoints.get_audit_logs(limit=100, skip=0, resourceType=None, resourceId=None, actor=None,
                                                          action="b.", outcome=None, catalogue=None, from_=None, to=None,
                                                          tenantId="tenant-b", current_user=root)
            csv_resp = await audit_endpoints.export_audit_logs(
                SimpleNamespace(client=SimpleNamespace(host="10.0.0.1")), actor=None, action=None, outcome=None,
                catalogue=None, from_=None, to=None, tenantId="tenant-b", current_user=root)
    assert [e["action"] for e in mine] == ["a.write"]
    assert [e["action"] for e in theirs] == ["b.write"]
    body = "".join([chunk async for chunk in csv_resp.body_iterator])
    assert "b.write" in body and "a.write" not in body
    assert await live_db.audit_logs.count_documents({"action": "export.audit_log", "tenantId": "tenant-b"}) == 1


async def test_legacy_writers_write_the_one_chained_schema(live_db):
    """protects=audit_service.log_action_async and audit.log_event land in the same chain."""
    import audit
    from audit_service import get_audit_service
    await get_audit_service().log_action_async("bob", "license.changed", "agent_license", "tenant-a", "x", tenant_id="tenant-a")
    assert await audit.audit_service.log_event("rag_ingest", "carol", "doc-1", {"n": 1}, tenant_id="tenant-a")
    entries = await _entries(live_db, tenantId="tenant-a")
    assert [(e["seq"], e["action"]) for e in entries] == [(1, "license.changed"), (2, "rag_ingest")]
    assert all({"actor", "outcome", "hash", "previousHash"} <= e.keys() for e in entries)
    assert (await audit_ledger.verify("tenant-a", db=live_db))["valid"]


async def test_middleware_overhead_stays_within_ten_ms_p95(live_db):
    """AC8. protects=p95 latency of 200 PATCHes rises by at most 10 ms with auditing on.
    no_claim=production timing (local Mongo, in-process client; the write is included)."""
    headers = {"Authorization": f"Bearer {_token()}"}

    async def p95(app):
        times = []
        async with _client(app) as c:
            for i in range(200):
                t0 = time.perf_counter()
                await c.patch(f"/api/tickets/t-{i}", json={"status": "open"}, headers=headers)
                times.append((time.perf_counter() - t0) * 1000)
        return statistics.quantiles(times, n=20)[-1]

    base, audited = await p95(_app(audited=False)), await p95(_app(audited=True))
    print(f"p95 without audit {base:.2f} ms, with audit {audited:.2f} ms")
    assert audited - base <= 10, (base, audited)
