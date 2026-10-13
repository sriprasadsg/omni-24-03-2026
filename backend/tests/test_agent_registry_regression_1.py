"""
Regression: ISSUE-001 — concurrent first enrollments exceed the tenant agent limit
Found by /qa on 2026-10-13
Report: .gstack/qa-reports/run-20261013T151919Z/qa-report-127.0.0.1-2026-10-13.md

Live repro: tenant at 4/5, five concurrent POST /api/agents/register → 3 (then 5)
succeeded, tenant ended at 9/5. The seat check (count_documents) and the insert
(upsert) ran without anything serializing them.

Value: protects=five concurrent first enrollments at 4/5 admit exactly one and leave
the tenant at 5; fails_when=the count and the upsert are not serialized per tenant;
why_new=test_agent_identity.py covers re-enrollment identity only, nothing covers the
limit under concurrency; seam=none; no_claim=real Mongo lease timing across workers
(in-memory async fakes stand in for the agents/assets/lock collections, E11000 simulated).
Hermetic: no Mongo.
"""
import asyncio
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import agent_registry_endpoints as reg

TENANT = {"id": "tenant-a", "registrationKey": "k", "maxAgents": 5}


class _Result:
    def __init__(self, matched=0, upserted_id=None, deleted=0):
        self.matched_count = matched
        self.modified_count = matched
        self.upserted_id = upserted_id
        self.deleted_count = deleted


def _matches(doc, flt):
    for key, cond in flt.items():
        if isinstance(cond, dict) and "$lt" in cond:
            if key not in doc or not doc[key] < cond["$lt"]:
                return False
        elif doc.get(key) != cond:
            return False
    return True


class _FakeCollection:
    """Async in-memory collection that yields to the loop on every call, so
    concurrent requests interleave the way they do against a real server."""

    def __init__(self, docs=None, key="id"):
        self.docs = list(docs or [])
        self.key = key

    async def find_one(self, flt, *_a, **_k):
        await asyncio.sleep(0)
        return next((dict(d) for d in self.docs if _matches(d, flt)), None)

    async def count_documents(self, flt, *_a, **_k):
        await asyncio.sleep(0)
        return sum(1 for d in self.docs if _matches(d, flt))

    async def update_one(self, flt, update, upsert=False, **_k):
        await asyncio.sleep(0)
        for d in self.docs:
            if _matches(d, flt):
                d.update(update.get("$set", {}))
                return _Result(matched=1)
        if not upsert:
            return _Result()
        new = {k: v for k, v in flt.items() if not isinstance(v, dict)}
        if any(d.get(self.key) == new.get(self.key) for d in self.docs if self.key in new):
            raise Exception("E11000 duplicate key error collection: fake")
        new.update(update.get("$set", {}))
        self.docs.append(new)
        return _Result(upserted_id=new.get(self.key))

    async def delete_one(self, flt, *_a, **_k):
        await asyncio.sleep(0)
        for i, d in enumerate(self.docs):
            if _matches(d, flt):
                del self.docs[i]
                return _Result(deleted=1)
        return _Result()


def _db(existing_agents):
    db = MagicMock()
    db.tenants = _FakeCollection([TENANT])
    db.agents = _FakeCollection(existing_agents)
    db.assets = _FakeCollection()
    db._db.enrollment_locks = _FakeCollection(key="_id")
    return db


def _request():
    return Request({"type": "http", "method": "POST", "path": "/api/agents/register", "headers": []})


async def test_concurrent_first_enrollments_cannot_exceed_agent_limit():
    existing = [{"id": f"agent-{i}", "tenantId": "tenant-a", "hostname": f"old-{i}"} for i in range(4)]
    db = _db(existing)
    stub_finops = types.SimpleNamespace(
        finops_service=types.SimpleNamespace(recalculate_tenant_costs=AsyncMock()))

    async def _register(i):
        body = {"registrationKey": "k", "hostname": f"race-{i}", "platform": "Linux"}
        try:
            await reg.register_agent(_request(), MagicMock(), body, background_tasks=MagicMock())
            return "ok"
        except HTTPException as exc:
            return exc.status_code

    with patch.object(reg, "get_database", return_value=db), \
            patch.object(reg.limiter, "enabled", False), \
            patch.object(reg, "invalidate_cache"), \
            patch.dict(sys.modules, {"finops_service": stub_finops}):
        results = await asyncio.gather(*(_register(i) for i in range(5)))

    assert results.count("ok") == 1, results
    assert results.count(403) == 4, results
    assert await db.agents.count_documents({"tenantId": "tenant-a"}) == 5
    assert db._db.enrollment_locks.docs == []  # every lock was released
