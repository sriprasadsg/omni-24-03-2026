"""GET /api/itam/costs/assets - Phase 78 Plan 03 (COST-03, COST-06, COST-07).

Real throwaway MongoDB (mongo_db fixture) behind the production TenantIsolatedDatabase wrapper,
like the summary tests. Only the clock is patched. The route tests reuse the summary suite's
app / client helpers.
"""
import os
import sys
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests._mongo_test_db import mongo_db  # noqa: F401 - fixture re-exported for pytest
from tests.test_itam_cost_endpoints import (  # noqa: F401 - autouse fixtures must be visible here
    FIXED_NOW, _app, _client, _clean_ambient_tenant, _fixed_clock, _owner, _tenant_admin,
)

import database
import itam_asset_endpoints
import itam_cost_endpoints

LIST_URL = "/api/itam/costs/assets"
SUMMARY_URL = "/api/itam/costs/summary"
PURCHASE = (FIXED_NOW - timedelta(days=400)).isoformat()


def _asset(tenant, asset_id, *, name=None, tag=None, status="deployed", cost=None, date=None,
           model_id=None, hardware_key=None, serial=None, agent_status=None):
    doc = {"tenantId": tenant, "id": asset_id, "name": name or asset_id,
           "assetTag": tag if tag is not None else f"TAG-{asset_id}", "lifecycleStatus": status}
    for key, value in (("purchaseCostCents", cost), ("purchaseDate", date), ("modelId", model_id),
                       ("hardwareKey", hardware_key), ("serialNumber", serial), ("agentStatus", agent_status)):
        if value is not None:
            doc[key] = value
    return doc


def _agent(tenant, agent_id, asset_id, hostname, *, status="Online", last_seen="2026-11-16T10:00:00Z"):
    return {"tenantId": tenant, "id": agent_id, "assetId": asset_id, "hostname": hostname,
            "status": status, "lastSeen": last_seen}


async def _seed(db):
    await db.asset_models.insert_many([
        {"tenantId": "tenant-a", "id": "model-ok", "usefulLifeYears": 3, "salvageValueCents": 10000},
    ])
    await db.assets.insert_many([
        _asset("tenant-a", "M1", name="M1", cost=120000, date=PURCHASE, model_id="model-ok"),
        _asset("tenant-a", "P1", name="P1", cost=50000, date=PURCHASE, model_id="model-missing"),
        _asset("tenant-a", "AG1", name="AG1-laptop", hardware_key="serial:AG1SERIAL", agent_status="Online"),
        _asset("tenant-a", "D1", name="D1", status="disposed", cost=90000, date=PURCHASE, model_id="model-ok"),
        _asset("tenant-b", "BA1", name="BA1", cost=777000, date=PURCHASE),
    ])
    await db.agents.insert_many([
        _agent("tenant-a", "agent-1", "AG1", "ag-host", status="Offline"),
        _agent("tenant-b", "agent-b1", "BA1", "b-host"),
        _agent("tenant-b", "agent-b2", "AG1", "b-host-2"),  # a foreign agent naming tenant-a's asset
    ])


async def _get(monkeypatch, db, params=None, user=None, url=LIST_URL, headers=None):
    app = _app(monkeypatch, db)
    async with _client(app, user or _tenant_admin()) as ac:
        return await ac.get(url, params=params, headers=headers)


async def _walk(monkeypatch, db, page_size, **params):
    """Every page of the list, in order."""
    items, page = [], 1
    while True:
        r = await _get(monkeypatch, db, {"page": page, "page_size": page_size, **params})
        assert r.status_code == 200, r.text
        body = r.json()
        items.extend(body["items"])
        if not body["hasNext"]:
            return items, body
        page += 1


class TestListTracer:
    @pytest.mark.asyncio
    async def test_list_tracer_real_mongo(self, mongo_db, monkeypatch):
        await _seed(mongo_db)
        r = await _get(monkeypatch, mongo_db)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] == 3 and body["tenantId"] == "tenant-a"
        assert body["includeDisposed"] is False and body["agentOnly"] is False
        assert body["computedAt"] == FIXED_NOW.isoformat(timespec="milliseconds")
        assert [row["assetId"] for row in body["items"]] == ["M1", "AG1", "P1"]
        agent_row = body["items"][1]
        assert agent_row["bookValueCents"] is None and agent_row["reason"] == "no_purchase_record"
        assert agent_row["agent"]["status"] == "Offline"  # not the asset's own "Online"
        assert agent_row["agent"]["agentId"] == "agent-1" and agent_row["agent"]["agentCount"] == 1
        assert body["items"][0]["agent"] is None
        assert "BA1" not in r.text and "agent-b" not in r.text and "tenant-b" not in r.text

    @pytest.mark.asyncio
    async def test_list_adds_up_to_summary(self, mongo_db, monkeypatch):
        await _seed(mongo_db)
        for include in ("false", "true"):
            rows, _ = await _walk(monkeypatch, mongo_db, 2, includeDisposed=include)
            r = await _get(monkeypatch, mongo_db, {"includeDisposed": include}, url=SUMMARY_URL)
            summary = r.json()
            assert len(rows) == summary["coverage"]["total"]
            purchase = [x["purchaseCostCents"] for x in rows if x["purchaseCostCents"] is not None]
            book = [x["bookValueCents"] for x in rows if x["bookValueCents"] is not None]
            assert sum(purchase) == summary["purchaseTotal"]["cents"]
            assert sum(book) == summary["bookValueTotal"]["cents"]

    @pytest.mark.asyncio
    async def test_include_disposed_rows(self, mongo_db, monkeypatch):
        await _seed(mongo_db)
        r = await _get(monkeypatch, mongo_db, {"includeDisposed": "true"})
        body = r.json()
        assert body["total"] == 4 and body["includeDisposed"] is True
        disposed = [x for x in body["items"] if x["assetId"] == "D1"][0]
        assert disposed["lifecycleStatus"] == "disposed" and disposed["purchaseCostCents"] == 90000
        assert disposed["bookValueCents"] is None and disposed["reason"] == "disposed"

    @pytest.mark.asyncio
    async def test_agent_only_filter(self, mongo_db, monkeypatch):
        await _seed(mongo_db)
        r = await _get(monkeypatch, mongo_db, {"agentOnly": "true"})
        body = r.json()
        assert body["agentOnly"] is True and body["total"] == 1
        assert [x["assetId"] for x in body["items"]] == ["AG1"]

    @pytest.mark.asyncio
    async def test_two_agents_one_asset_single_row(self, mongo_db, monkeypatch):
        await _seed(mongo_db)
        await mongo_db.agents.insert_one(
            _agent("tenant-a", "agent-2", "AG1", "ag-host-2", status="Online", last_seen="2026-11-16T11:00:00Z"))
        r = await _get(monkeypatch, mongo_db)
        rows = [x for x in r.json()["items"] if x["assetId"] == "AG1"]
        assert len(rows) == 1
        assert rows[0]["agent"]["agentId"] == "agent-2" and rows[0]["agent"]["agentCount"] == 2

    @pytest.mark.asyncio
    async def test_hostname_only_match_gets_no_agent(self, mongo_db, monkeypatch):
        await _seed(mongo_db)
        await mongo_db.agents.insert_one(_agent("tenant-a", "agent-3", "elsewhere", "P1"))  # hostname == asset name
        r = await _get(monkeypatch, mongo_db)
        row = [x for x in r.json()["items"] if x["assetId"] == "P1"][0]
        assert row["agent"] is None


class TestPaging:
    @pytest.mark.asyncio
    async def test_page_walk_is_complete_and_stable(self, mongo_db, monkeypatch):
        await mongo_db.assets.insert_many(
            [_asset("tenant-a", f"id-{i}", name=name, tag=tag) for i, (name, tag) in enumerate([
                ("same", "T2"), ("same", "T1"), ("same", "T1"), ("alpha", "T9"), ("beta", ""), ("same", "T3"), ("zeta", "T0"),
            ])])
        first, body = await _walk(monkeypatch, mongo_db, 3)
        second, _ = await _walk(monkeypatch, mongo_db, 3)
        ids = [x["assetId"] for x in first]
        assert sorted(ids) == sorted(f"id-{i}" for i in range(7)) and len(ids) == len(set(ids))
        assert ids == [x["assetId"] for x in second] and body["total"] == 7
        assert first == sorted(first, key=lambda x: (x["name"], x["assetTag"], x["assetId"]))

    @pytest.mark.asyncio
    async def test_page_size_cap(self, mongo_db, monkeypatch):
        await _seed(mongo_db)
        assert (await _get(monkeypatch, mongo_db, {"page_size": 101})).status_code == 422
        r = await _get(monkeypatch, mongo_db, {"page": 99, "page_size": 2})
        assert r.status_code == 200 and r.json()["items"] == [] and r.json()["total"] == 3

    @pytest.mark.asyncio
    async def test_empty_tenant_list(self, mongo_db, monkeypatch):
        r = await _get(monkeypatch, mongo_db, user=_tenant_admin("tenant-empty"))
        assert r.status_code == 200
        assert r.json()["total"] == 0 and r.json()["items"] == []

    @pytest.mark.asyncio
    async def test_list_reads_each_collection_once(self, mongo_db, monkeypatch):
        await _seed(mongo_db)
        counts = {}
        real = database.TenantIsolatedDatabase(mongo_db)

        class _Counting:
            def __getattr__(self, name):
                collection = getattr(real, name)
                find = collection.find

                def counted(*args, **kwargs):
                    counts[name] = counts.get(name, 0) + 1
                    return find(*args, **kwargs)

                return type("C", (), {"find": staticmethod(counted)})()

        app = _app(monkeypatch)
        monkeypatch.setattr(itam_cost_endpoints, "get_database", lambda: _Counting())
        async with _client(app, _tenant_admin()) as ac:
            r = await ac.get(LIST_URL)
        assert r.status_code == 200, r.text
        assert counts == {"assets": 1, "asset_models": 1, "agents": 1}


class TestGuardAndTenant:
    @pytest.mark.asyncio
    async def test_list_owner_without_tenant_is_400(self, monkeypatch):
        app = _app(monkeypatch)
        async with _client(app, _owner()) as ac:
            r = await ac.get(LIST_URL)
        assert r.status_code == 400 and r.json()["detail"].startswith("Select a tenant")

    @pytest.mark.asyncio
    async def test_list_403_without_view_itam(self, monkeypatch):
        monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=False))
        app = _app(monkeypatch, permission_ok=False)
        async with _client(app, _tenant_admin()) as ac:
            r = await ac.get(LIST_URL)
        assert r.status_code == 403
