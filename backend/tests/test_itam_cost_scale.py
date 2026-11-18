"""Large-tenant read bound for the cost surfaces - Phase 78 Plan 08, Task 2 (COST-07, D-08).

The whole tenant set is computed, then paged, so the cost of a request grows with the tenant. This
pins that a 20,000-asset tenant is served with a fixed number of reads per collection (never one
per asset) inside a time bound, and that a second tenant's assets are never read into the figures.
Real throwaway MongoDB behind the production TenantIsolatedDatabase wrapper; only the clock is patched.
"""
import os
import sys
import time
from datetime import timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests._mongo_test_db import mongo_db  # noqa: F401 - fixture re-exported for pytest
from tests.test_itam_cost_endpoints import (  # noqa: F401 - autouse fixtures must be visible here
    FIXED_NOW, _app, _client, _clean_ambient_tenant, _fixed_clock, _tenant_admin,
)

import database
import itam_cost_endpoints
import tenant_context
from itam_reporting_kpis import compute_itam_kpis

TENANT_S_ASSETS = 20000
TENANT_S_DISPOSED = 500
TENANT_S_AGENTS = 2000
TENANT_T_ASSETS = 1000
IN_SCOPE = TENANT_S_ASSETS - TENANT_S_DISPOSED  # 19,500
LIST_SECONDS = 10.0
BATCH = 5000


def _s_asset(i):
    doc = {
        "tenantId": "tenant-s", "id": f"s-{i}", "assetTag": f"S-{i:05d}", "name": f"Laptop {i % 700}",
        "lifecycleStatus": "disposed" if i % 40 == 0 else ("deployed" if i % 2 else "deployable"),
        "purchaseCostCents": 100000 + i,
        "purchaseDate": (FIXED_NOW - timedelta(days=30 + i % 1500)).isoformat(),
        "modelId": "model-pol" if i % 3 == 0 else "model-nopol",
    }
    return doc


async def _seed_large(db):
    await db.asset_models.insert_many([
        {"tenantId": "tenant-s", "id": "model-pol", "usefulLifeYears": 4, "salvageValueCents": 5000},
        {"tenantId": "tenant-s", "id": "model-nopol"},
        {"tenantId": "tenant-t", "id": "model-pol", "usefulLifeYears": 1, "salvageValueCents": 0},
    ])
    for start in range(0, TENANT_S_ASSETS, BATCH):
        await db.assets.insert_many([_s_asset(i) for i in range(start, min(start + BATCH, TENANT_S_ASSETS))])
    await db.assets.insert_many([
        {"tenantId": "tenant-t", "id": f"t-{i}", "assetTag": f"T-{i:05d}", "name": f"Other {i}",
         "lifecycleStatus": "deployed", "purchaseCostCents": 999999,
         "purchaseDate": (FIXED_NOW - timedelta(days=100)).isoformat(), "modelId": "model-pol"}
        for i in range(TENANT_T_ASSETS)
    ])
    linked = [i for i in range(TENANT_S_ASSETS) if i % 10 == 1][:TENANT_S_AGENTS]
    assert len(linked) == TENANT_S_AGENTS and all(i % 40 != 0 for i in linked)
    await db.agents.insert_many([
        {"tenantId": "tenant-s", "id": f"agent-{i}", "assetId": f"s-{i}", "hostname": f"host-{i}",
         "status": "Online", "lastSeen": "2026-11-16T10:00:00Z"}
        for i in linked
    ])


class _CountedCollection:
    def __init__(self, collection, counts, name):
        self._collection, self._counts, self._name = collection, counts, name

    def find(self, *args, **kwargs):
        self._counts[self._name] = self._counts.get(self._name, 0) + 1
        return self._collection.find(*args, **kwargs)

    def __getattr__(self, attr):
        return getattr(self._collection, attr)


class _CountingDb:
    """The tenant-isolated database with every collection's find counted."""

    def __init__(self, raw_db):
        self._real = database.TenantIsolatedDatabase(raw_db)
        self.counts = {}

    def __getattr__(self, name):
        return _CountedCollection(getattr(self._real, name), self.counts, name)


async def _get(monkeypatch, counting, url, params=None):
    app = _app(monkeypatch)
    monkeypatch.setattr(itam_cost_endpoints, "get_database", lambda: counting)
    async with _client(app, _tenant_admin("tenant-s")) as ac:
        started = time.perf_counter()
        response = await ac.get(url, params=params)
        elapsed = time.perf_counter() - started
    assert response.status_code == 200, response.text
    return response.json(), elapsed


@pytest.mark.asyncio
async def test_large_tenant_reads_are_bounded(mongo_db, monkeypatch):
    await _seed_large(mongo_db)

    summary_db = _CountingDb(mongo_db)
    summary, summary_seconds = await _get(monkeypatch, summary_db, "/api/itam/costs/summary")
    assert summary_db.counts.get("assets") == 1
    assert summary_db.counts.get("asset_models", 0) <= 1
    assert "agents" not in summary_db.counts
    assert summary_db.counts.get("licenses") == 1 and summary_db.counts.get("license_assignments") == 1
    assert summary["coverage"]["total"] == IN_SCOPE
    assert summary["coverage"]["excludedByLifecycle"] == TENANT_S_DISPOSED

    list_db = _CountingDb(mongo_db)
    listing, list_seconds = await _get(monkeypatch, list_db, "/api/itam/costs/assets", {"page": 1, "page_size": 100})
    # Phase 79: the license spend adds one read each of licenses and license_assignments.
    assert list_db.counts == {"assets": 1, "asset_models": 1, "agents": 1, "licenses": 1, "license_assignments": 1}
    assert listing["total"] == IN_SCOPE and len(listing["items"]) == 100
    assert listing["hasNext"] is True

    kpi_db = _CountingDb(mongo_db)
    token = tenant_context.set_tenant_id("tenant-s")
    try:
        started = time.perf_counter()
        kpi = await compute_itam_kpis(kpi_db, "tenant-s")
        kpi_seconds = time.perf_counter() - started
    finally:
        tenant_context.reset_tenant_id(token)
    assert kpi_db.counts.get("asset_models") == 1
    # The overdue KPI reads assets twice more for its audit and check-in rows; only the cost read is bounded here.
    assert kpi["assetValue"]["assetCount"] == TENANT_S_ASSETS
    assert kpi["assetValue"]["inScopeAssetCount"] == IN_SCOPE

    # One tenant's figures only: the summary, the list page and the KPI agree and never carry tenant-t.
    assert kpi["assetValue"]["totalBookValueCents"] == summary["bookValueTotal"]["cents"]
    assert kpi["assetValue"]["valuedCount"] == summary["coverage"]["valued"]
    assert summary["purchaseTotal"]["cents"] != 0
    assert all(item["assetId"].startswith("s-") for item in listing["items"])
    assert "tenant-t" not in repr(summary) + repr(listing)
    assert summary["tenantId"] == "tenant-s" and listing["tenantId"] == "tenant-s"

    print(
        f"\nCOST SCALE ({TENANT_S_ASSETS} assets, {IN_SCOPE} in scope): "
        f"summary {summary_seconds:.2f}s, list page 1 {list_seconds:.2f}s, KPI {kpi_seconds:.2f}s"
    )
    assert list_seconds < LIST_SECONDS, f"list took {list_seconds:.2f}s (bound {LIST_SECONDS}s)"
