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
        # Phase 79: the license spend adds one read each of licenses and license_assignments.
        assert counts == {"assets": 1, "asset_models": 1, "agents": 1, "licenses": 1, "license_assignments": 1}


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


def _flagged(rows):
    return {r["assetId"]: r for r in rows if "possibleDuplicate" in r["flags"]}


async def _rows(monkeypatch, db, **params):
    r = await _get(monkeypatch, db, params)
    assert r.status_code == 200, r.text
    return r.json()["items"]


class TestPossibleDuplicates:
    @pytest.mark.asyncio
    async def test_serial_duplicate_pair_marked(self, mongo_db, monkeypatch):
        await mongo_db.assets.insert_many([
            _asset("tenant-a", "AGX", hardware_key="serial:ABC123", cost=30000, date=PURCHASE),
            _asset("tenant-a", "MAN", serial=" abc123 ", cost=40000, date=PURCHASE),
        ])
        rows = await _rows(monkeypatch, mongo_db)
        flagged = _flagged(rows)
        assert set(flagged) == {"AGX", "MAN"}
        assert flagged["AGX"]["possibleDuplicateOf"] == ["MAN"] and flagged["MAN"]["possibleDuplicateOf"] == ["AGX"]
        assert flagged["AGX"]["purchaseCostCents"] == 30000 and flagged["MAN"]["purchaseCostCents"] == 40000
        summary = (await _get(monkeypatch, mongo_db, url=SUMMARY_URL)).json()
        assert summary["purchaseTotal"]["cents"] == 70000 and summary["coverage"]["total"] == 2
        assert summary["coverage"]["possibleDuplicatePairs"] == 1
        assert summary["coverage"]["flags"]["possibleDuplicate"] == 2

    @pytest.mark.asyncio
    async def test_placeholder_serials_never_match(self, mongo_db, monkeypatch):
        await mongo_db.assets.insert_many([
            _asset("tenant-a", "AG1", hardware_key="serial:To Be Filled By O.E.M."),
            _asset("tenant-a", "MAN1", serial="To Be Filled By O.E.M."),
            _asset("tenant-a", "AG2", hardware_key="serial:0000000"),
            _asset("tenant-a", "MAN2", serial="0000000"),
        ])
        rows = await _rows(monkeypatch, mongo_db)
        assert _flagged(rows) == {} and all(r["possibleDuplicateOf"] == [] for r in rows)

    @pytest.mark.asyncio
    async def test_uuid_and_mac_keys_never_match(self, mongo_db, monkeypatch):
        await mongo_db.assets.insert_many([
            _asset("tenant-a", "AGU", hardware_key="uuid:ABC123"),
            _asset("tenant-a", "AGM", hardware_key="mac:ABC123"),
            _asset("tenant-a", "MAN", serial="ABC123"),
        ])
        assert _flagged(await _rows(monkeypatch, mongo_db)) == {}

    @pytest.mark.asyncio
    async def test_two_agent_assets_same_serial_not_paired(self, mongo_db, monkeypatch):
        await mongo_db.assets.insert_many([
            _asset("tenant-a", "AG1", hardware_key="serial:XYZ789"),
            _asset("tenant-a", "AG2", hardware_key="serial:XYZ789"),
        ])
        assert _flagged(await _rows(monkeypatch, mongo_db)) == {}

    @pytest.mark.asyncio
    async def test_markers_are_stable_when_the_twin_is_retired(self, mongo_db, monkeypatch):
        # WR-03: markers span every asset of the tenant, so list (both scopes), detail and summary agree.
        await mongo_db.assets.insert_many([
            _asset("tenant-a", "AGX", hardware_key="serial:ABC123", status="retired", cost=100, date=PURCHASE),
            _asset("tenant-a", "MAN", serial="abc123", cost=200, date=PURCHASE),
        ])
        default_rows = await _rows(monkeypatch, mongo_db)
        all_rows = await _rows(monkeypatch, mongo_db, includeDisposed="true")
        assert [r["assetId"] for r in default_rows] == ["MAN"]
        man_default = default_rows[0]
        man_all = [r for r in all_rows if r["assetId"] == "MAN"][0]
        assert man_default["possibleDuplicateOf"] == ["AGX"] and "possibleDuplicate" in man_default["flags"]
        assert man_default == man_all
        detail = (await _get(monkeypatch, mongo_db, url=f"{LIST_URL}/MAN")).json()
        detail.pop("computedAt")
        assert detail == man_default
        retired_detail = (await _get(monkeypatch, mongo_db, url=f"{LIST_URL}/AGX")).json()
        assert retired_detail["possibleDuplicateOf"] == ["MAN"] and "possibleDuplicate" in retired_detail["flags"]
        # A pair with one in-scope member counts once under either scope.
        for params, flagged in (({}, 1), ({"includeDisposed": "true"}, 2)):
            coverage = (await _get(monkeypatch, mongo_db, params, url=SUMMARY_URL)).json()["coverage"]
            assert coverage["possibleDuplicatePairs"] == 1, params
            assert coverage["flags"]["possibleDuplicate"] == flagged, params

    @pytest.mark.asyncio
    async def test_pair_of_two_out_of_scope_assets_is_not_counted_by_default(self, mongo_db, monkeypatch):
        await mongo_db.assets.insert_many([
            _asset("tenant-a", "AGX", hardware_key="serial:ABC123", status="disposed"),
            _asset("tenant-a", "OLD", serial="abc123", status="retired"),
        ])
        assert await _rows(monkeypatch, mongo_db) == []
        default = (await _get(monkeypatch, mongo_db, url=SUMMARY_URL)).json()["coverage"]
        assert default["possibleDuplicatePairs"] == 0
        both = (await _get(monkeypatch, mongo_db, {"includeDisposed": "true"}, url=SUMMARY_URL)).json()["coverage"]
        assert both["possibleDuplicatePairs"] == 1


class TestDetail:
    @pytest.mark.asyncio
    async def test_detail_returns_list_row(self, mongo_db, monkeypatch):
        await _seed(mongo_db)
        rows = await _rows(monkeypatch, mongo_db, includeDisposed="true")
        r = await _get(monkeypatch, mongo_db, url=f"{LIST_URL}/M1")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.pop("computedAt") == FIXED_NOW.isoformat(timespec="milliseconds")
        assert body == [x for x in rows if x["assetId"] == "M1"][0]
        assert body["bookValueCents"] is not None
        agent = (await _get(monkeypatch, mongo_db, url=f"{LIST_URL}/AG1")).json()
        assert agent["agent"]["agentId"] == "agent-1"

    @pytest.mark.asyncio
    async def test_detail_disposed_asset(self, mongo_db, monkeypatch):
        await _seed(mongo_db)
        r = await _get(monkeypatch, mongo_db, url=f"{LIST_URL}/D1")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["bookValueCents"] is None and body["reason"] == "disposed" and body["purchaseCostCents"] == 90000

    @pytest.mark.asyncio
    async def test_detail_carries_duplicate_markers(self, mongo_db, monkeypatch):
        await mongo_db.assets.insert_many([
            _asset("tenant-a", "AGX", hardware_key="serial:ABC123"), _asset("tenant-a", "MAN", serial="abc123"),
        ])
        body = (await _get(monkeypatch, mongo_db, url=f"{LIST_URL}/MAN")).json()
        assert body["possibleDuplicateOf"] == ["AGX"] and "possibleDuplicate" in body["flags"]

    @pytest.mark.asyncio
    async def test_foreign_and_unknown_asset_ids_are_identical_404s(self, mongo_db, monkeypatch):
        await _seed(mongo_db)
        foreign = await _get(monkeypatch, mongo_db, url=f"{LIST_URL}/BA1")
        unknown = await _get(monkeypatch, mongo_db, url=f"{LIST_URL}/no-such-asset")
        assert foreign.status_code == 404 and unknown.status_code == 404
        assert foreign.content == unknown.content
        assert foreign.json() == {"detail": "Asset not found"}
        assert "777000" not in foreign.text

    @pytest.mark.asyncio
    async def test_foreign_asset_id_is_404(self, mongo_db, monkeypatch):
        await _seed(mongo_db)
        r = await _get(monkeypatch, mongo_db, url=f"{LIST_URL}/BA1")
        assert r.status_code == 404 and r.json()["detail"] == "Asset not found"

    @pytest.mark.asyncio
    async def test_unknown_asset_id_is_404(self, mongo_db, monkeypatch):
        r = await _get(monkeypatch, mongo_db, url=f"{LIST_URL}/nope")
        assert r.status_code == 404 and r.json() == {"detail": "Asset not found"}

    @pytest.mark.asyncio
    async def test_detail_owner_without_tenant_is_400(self, monkeypatch):
        app = _app(monkeypatch)
        async with _client(app, _owner()) as ac:
            r = await ac.get(f"{LIST_URL}/M1")
        assert r.status_code == 400


def test_cost_asset_routes_enforced_on_real_app():
    from tests._route_walk import probe_real_app

    def case(path, role, auth="session_capable", scopes=None):
        c = {"method": "GET", "path": path, "role": role, "tenant_id": "tenant-a", "auth": auth}
        if scopes is not None:
            c["scopes"] = scopes
        return c

    paths = ["/api/itam/costs/assets", "/api/itam/costs/assets/a1"]
    cases = [case(p, "nobody") for p in paths] + [case(p, "itam_viewer", "api_key", ["view:itam"]) for p in paths]
    statuses = probe_real_app(cases)
    assert statuses[:2] == [403, 403], statuses
    assert 403 not in statuses[2:], statuses
