"""
Regression: ISSUE-001 — concurrent first enrollments exceed the tenant agent limit
Found by /qa on 2026-10-13
Report: .gstack/qa-reports/run-20261013T151919Z/qa-report-127.0.0.1-2026-10-13.md

Live repro: tenant at 4/5, five concurrent POST /api/agents/register → 3 (then 5)
succeeded, tenant ended at 9/5. Fixed first by a per-tenant lease lock, then by the
spec C2 atomic seat counter (license.seatsUsed, conditional $inc); this test now runs
against a real MongoDB so the atomic claim itself is exercised. Since spec C3 the four
refused enrollments are kept as Pending records (no seat) instead of vanishing.

Value: protects=five concurrent first enrollments at 4/5 admit exactly one and leave
the tenant at 5 seats and 5 seat-holding agents (the other 4 Pending); fails_when=the seat check and the insert are not
atomic per tenant; why_new=test_agent_identity.py covers re-enrollment identity only;
seam=none; no_claim=multi-worker timing (one event loop, one server) and the HTTP layer
(register_agent is called directly). Skips without a reachable MongoDB.
"""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from starlette.requests import Request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import agent_registry_endpoints as reg
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)


def _request():
    return Request({"type": "http", "method": "POST", "path": "/api/agents/register", "headers": []})


async def test_concurrent_first_enrollments_cannot_exceed_agent_limit(mongo_db):
    await mongo_db.tenants.insert_one({"id": "tenant-a", "registrationKey": "k", "maxAgents": 5})
    await mongo_db.agents.insert_many([
        {"id": f"agent-{i}", "tenantId": "tenant-a", "hostname": f"old-{i}", "status": "Online"} for i in range(4)
    ])
    stub = MagicMock()
    stub.finops_service.recalculate_tenant_costs = AsyncMock()

    async def _register(i):
        body = {"registrationKey": "k", "hostname": f"race-{i}", "platform": "Linux"}
        try:
            await reg.register_agent(_request(), MagicMock(), body, background_tasks=MagicMock())
            return "ok"
        except HTTPException as exc:
            return exc.status_code

    with patch.object(reg, "get_database", return_value=mongo_db), \
            patch.object(reg.limiter, "enabled", False), \
            patch.object(reg, "invalidate_cache"), \
            patch.dict(sys.modules, {"finops_service": stub}):
        results = await asyncio.gather(*(_register(i) for i in range(5)))

    assert results.count("ok") == 1, results
    assert results.count(403) == 4, results
    assert await mongo_db.agents.count_documents({"tenantId": "tenant-a", "status": "Online"}) == 5
    assert await mongo_db.agents.count_documents({"tenantId": "tenant-a", "status": "Pending"}) == 4
    assert (await mongo_db.tenants.find_one({"id": "tenant-a"}))["license"]["seatsUsed"] == 5
