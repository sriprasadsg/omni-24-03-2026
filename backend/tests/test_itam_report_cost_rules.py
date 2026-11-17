"""ITAM report cost rules - Phase 78 Plan 05 (COST-01, COST-06, COST-07).

D-04 / D-01: the Asset value report drops disposed and retired assets. D-08: its rows follow
itam_cost_service.sort_cost_rows. COST-01: every row's figures come from compute_asset_cost at one
clock read. D-13: the pre-built run and export routes cover one resolved tenant, so a Super Admin
with no chosen tenant gets 400 before any database or file work. D-03: the custom builder's Book
Value column comes from the same computation (disposed or retired shows an em dash).
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.conftest import make_token_data
from tests.itam_reporting_test_support import (  # noqa: F401 - fixtures re-exported for pytest
    MockTenantIsolatedDatabase,
    mock_db,
    patch_reporting_get_database,
    report_asset,
    reporting_app,
)

import itam_cost_service
import itam_reporting_endpoints
import itam_reporting_prebuilt
import itam_reporting_service as reporting_service_module
import rbac_utils
import tenant_context
from api_key_auth import get_current_user_or_api_key
from authentication_service import get_current_user as real_get_current_user
from itam_cost_service import compute_asset_cost
from itam_reporting_filters import run_custom_report
from itam_reporting_prebuilt import _cents_to_dollars

FIXED_NOW = datetime(2026, 11, 16, 12, 0, 0, tzinfo=timezone.utc)
PURCHASE = (FIXED_NOW - timedelta(days=400)).isoformat()
MODEL = {"id": "model-1", "usefulLifeYears": 3, "salvageValueCents": 10000}
RUN = "/api/itam/reports/prebuilt/asset_value/run"
EXPORT = "/api/itam/reports/prebuilt/asset_value/export"


@pytest.fixture(autouse=True)
def _clean_ambient_tenant():
    """The resolver sets the ambient tenant in the handler's context; TenantMiddleware restores it
    in production, so a test app without that middleware must do it here."""
    token = tenant_context.set_tenant_id(None)
    yield
    tenant_context.reset_tenant_id(token)


@pytest.fixture(autouse=True)
def _fixed_clock(monkeypatch):
    monkeypatch.setattr(itam_cost_service, "utc_now", lambda: FIXED_NOW)


def _client(app, user=None):
    user = user or make_token_data(tenant_id="tenant-a", role="admin", username="admin@example.com")
    app.dependency_overrides[get_current_user_or_api_key] = lambda: user
    app.dependency_overrides[real_get_current_user] = lambda: user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


def _owner():
    return make_token_data(role="Super Admin", tenant_id="platform-admin", username="owner@example.com")


def _asset(asset_id, status="deployed", **overrides):
    doc = report_asset(
        id=asset_id, assetTag=f"IT-{asset_id}", name=f"Laptop {asset_id}", lifecycleStatus=status,
        modelId="model-1", purchaseCostCents=120000, purchaseDate=PURCHASE,
    )
    doc.update(overrides)
    return doc


def _seed(mock_db, assets, models=(MODEL,)):
    mock_db.assets.find.return_value.to_list.return_value = assets
    mock_db.asset_models.find.return_value.to_list.return_value = list(models)


async def _run(app, user=None):
    async with _client(app, user) as ac:
        return await ac.post(RUN)


class TestAssetValueReportRules:
    @pytest.mark.asyncio
    async def test_asset_value_report_drops_disposed_and_retired(self, mock_db, reporting_app):
        no_status = _asset("a7")
        del no_status["lifecycleStatus"]  # genuinely absent -> deployable by default
        _seed(mock_db, [
            _asset("a1", "deployed"), _asset("a2", "archived"), _asset("a3", "broken"),
            _asset("a4", "retired"), _asset("a5", "disposed"), no_status,
        ])

        r = await _run(reporting_app)

        assert r.status_code == 200, r.text
        tags = sorted(row["Asset Tag"] for row in r.json()["rows"])
        assert tags == ["IT-a1", "IT-a2", "IT-a3", "IT-a7"]

    @pytest.mark.asyncio
    async def test_asset_value_rows_match_shared_computation(self, mock_db, reporting_app):
        assets = [
            _asset("a1", purchaseCostCents=250000, purchaseDate=(FIXED_NOW - timedelta(days=30)).isoformat()),
            _asset("a2"),
            _asset("a3", modelId="model-missing"),
        ]
        _seed(mock_db, assets)

        r = await _run(reporting_app)

        assert r.status_code == 200, r.text
        rows = {row["Asset Tag"]: row for row in r.json()["rows"]}
        assert len(rows) == 3
        for asset in assets:
            shared = compute_asset_cost(asset, MODEL if asset["modelId"] == "model-1" else None, FIXED_NOW)
            row = rows[asset["assetTag"]]
            assert row["Book Value"] == _cents_to_dollars(shared["bookValueCents"])
            assert row["Purchase Cost"] == _cents_to_dollars(shared["purchaseCostCents"])
            assert row["Years Elapsed"] == (shared["yearsElapsed"] if shared["yearsElapsed"] is not None else "—")
            assert row["Reason"] == (shared["reason"] or "—")

    @pytest.mark.asyncio
    async def test_asset_value_sort_tiebreak(self, mock_db, reporting_app):
        # Equal book value: name, then asset tag. The unvalued row (no model) sorts last even though
        # its name sorts first.
        _seed(mock_db, [
            _asset("z", name="Beta", assetTag="IT-2"),
            _asset("y", name="Beta", assetTag="IT-1"),
            _asset("x", name="Alpha", assetTag="IT-9"),
            _asset("w", name="Aaa", assetTag="IT-0", modelId="model-missing"),
        ])

        r = await _run(reporting_app)

        assert r.status_code == 200, r.text
        assert [row["Asset Tag"] for row in r.json()["rows"]] == ["IT-9", "IT-1", "IT-2", "IT-0"]

    @pytest.mark.asyncio
    async def test_malformed_inputs_do_not_fail_the_report(self, mock_db, reporting_app):
        _seed(mock_db, [
            _asset("bad-cost", purchaseCostCents="100000"),
            _asset("bad-date", purchaseDate="not-a-date"),
        ])

        r = await _run(reporting_app)

        assert r.status_code == 200, r.text
        rows = {row["Asset Tag"]: row for row in r.json()["rows"]}
        assert rows["IT-bad-cost"]["Purchase Cost"] == "—"
        assert rows["IT-bad-cost"]["Reason"] == "unreadable_purchase_cost"
        assert rows["IT-bad-date"]["Reason"] == "unreadable_purchase_date"
        assert rows["IT-bad-date"]["Book Value"] == "—"

    @pytest.mark.asyncio
    async def test_unhashable_lifecycle_status_reads_as_default(self, mock_db, reporting_app):
        # IN-02: a list or dict status must not raise TypeError (a 500 for the whole report).
        _seed(mock_db, [
            _asset("a-list", ["retired"]), _asset("a-dict", {"s": "disposed"}), _asset("a-ok", "retired"),
        ])

        r = await _run(reporting_app)

        assert r.status_code == 200, r.text
        assert sorted(row["Asset Tag"] for row in r.json()["rows"]) == ["IT-a-dict", "IT-a-list"]

    @pytest.mark.asyncio
    async def test_report_takes_one_clock_read_and_one_model_read(self, mock_db, reporting_app, monkeypatch):
        calls = []

        def _counting_clock():
            calls.append(1)
            return FIXED_NOW

        monkeypatch.setattr(itam_cost_service, "utc_now", _counting_clock)
        _seed(mock_db, [_asset("a1"), _asset("a2"), _asset("a3")])

        r = await _run(reporting_app)

        assert r.status_code == 200, r.text
        assert len(calls) == 1
        assert mock_db.asset_models.find.call_count == 1


def _never_db(monkeypatch):
    def _never():
        raise AssertionError("get_database must not be reached before the tenant is resolved")

    monkeypatch.setattr(itam_reporting_endpoints, "get_database", _never)
    monkeypatch.setattr(reporting_service_module, "get_database", _never)


class TestPrebuiltTenantResolution:
    @pytest.mark.asyncio
    async def test_prebuilt_run_owner_without_tenant_is_400(self, reporting_app, monkeypatch):
        _never_db(monkeypatch)
        async with _client(reporting_app, _owner()) as ac:
            r = await ac.post(RUN)
        assert r.status_code == 400
        assert r.json()["detail"].startswith("Select a tenant")

    @pytest.mark.asyncio
    async def test_prebuilt_export_owner_without_tenant_is_400(self, reporting_app, monkeypatch):
        _never_db(monkeypatch)
        async with _client(reporting_app, _owner()) as ac:
            r = await ac.post(EXPORT + "?format=csv")
        assert r.status_code == 400
        assert r.json()["detail"].startswith("Select a tenant")

    @pytest.mark.asyncio
    async def test_prebuilt_export_bad_format_still_needs_a_tenant(self, reporting_app, monkeypatch):
        # The resolver is the first statement, ahead of the format check.
        _never_db(monkeypatch)
        async with _client(reporting_app, _owner()) as ac:
            r = await ac.post(EXPORT + "?format=nope")
        assert r.status_code == 400
        assert r.json()["detail"].startswith("Select a tenant")

    @pytest.mark.asyncio
    async def test_prebuilt_run_every_report_key_needs_a_tenant(self, reporting_app, monkeypatch):
        _never_db(monkeypatch)
        async with _client(reporting_app, _owner()) as ac:
            for key in ("warranty_expiring", "checkout_activity", "overdue_audits",
                        "license_utilization", "low_stock_consumables"):
                r = await ac.post(f"/api/itam/reports/prebuilt/{key}/run")
                assert r.status_code == 400, key

    @pytest.mark.asyncio
    async def test_prebuilt_run_owner_header_uses_that_tenant(self, reporting_app, monkeypatch):
        seen = {}

        async def _spy(db, kind, key, tenant_id, definition=None, limit=None):
            seen["tenant_id"] = tenant_id
            seen["ambient"] = tenant_context.get_tenant_id()
            return {"key": key, "title": "t", "columns": ["c"], "rows": [], "rowCount": 0, "truncated": False}

        monkeypatch.setattr(itam_reporting_endpoints, "build_report_rows", _spy)
        async with _client(reporting_app, _owner()) as ac:
            r = await ac.post(RUN, headers={"X-Tenant-ID": "tenant-b"})

        assert r.status_code == 200, r.text
        assert seen == {"tenant_id": "tenant-b", "ambient": "tenant-b"}

    @pytest.mark.asyncio
    async def test_prebuilt_export_records_resolved_tenant(self, reporting_app, monkeypatch):
        generate = AsyncMock(return_value={"filename": "f.csv", "rowCount": 0})
        monkeypatch.setattr(reporting_service_module.itam_reporting_service, "generate", generate)
        async with _client(reporting_app, _owner()) as ac:
            r = await ac.post(EXPORT + "?format=csv", headers={"X-Tenant-ID": "tenant-b"})

        assert r.status_code == 200, r.text
        assert generate.await_args.kwargs["tenant_id"] == "tenant-b"

    @pytest.mark.asyncio
    async def test_tenant_admin_header_is_ignored(self, reporting_app, monkeypatch):
        seen = {}

        async def _spy(db, kind, key, tenant_id, definition=None, limit=None):
            seen["tenant_id"] = tenant_id
            return {"key": key, "title": "t", "columns": ["c"], "rows": [], "rowCount": 0, "truncated": False}

        monkeypatch.setattr(itam_reporting_endpoints, "build_report_rows", _spy)
        async with _client(reporting_app) as ac:
            r = await ac.post(RUN, headers={"X-Tenant-ID": "tenant-b"})

        assert r.status_code == 200, r.text
        assert seen["tenant_id"] == "tenant-a"

    @pytest.mark.asyncio
    async def test_prebuilt_run_support_is_403(self, mock_db, patch_reporting_get_database, monkeypatch):
        # D-15 amended 2026-11-16 (A-78-18): Platform Support holds no manage:assets, so the route
        # guard refuses it with 403 before the resolver could answer 400. Real verify_permission here.
        import rbac_defaults
        from tests.conftest import make_test_app

        assert "manage:assets" not in rbac_defaults.defaults_for("platform_support")
        monkeypatch.setattr(rbac_utils, "granted_permissions", AsyncMock(return_value=[]))
        app, _ = make_test_app(itam_reporting_endpoints.router)
        support = make_token_data(role="platform_support", tenant_id="platform-admin")
        async with _client(app, support) as ac:
            run = await ac.post(RUN, headers={"X-Tenant-ID": "tenant-a"})
            export = await ac.post(EXPORT + "?format=csv", headers={"X-Tenant-ID": "tenant-a"})
        assert run.status_code == 403
        assert export.status_code == 403


class TestCustomReportBookValue:
    """D-03 / A-78-16: the custom builder's Book Value column is the shared computation."""

    @staticmethod
    async def _custom(mock_db, assets):
        _seed(mock_db, assets)
        mock_db.license_assignments.find.return_value.to_list.return_value = []
        mock_db.components.find.return_value.to_list.return_value = []
        mock_db.itam_consumables.find.return_value.to_list.return_value = []
        mock_db.system_settings.find_one = AsyncMock(return_value=None)
        definition = {
            "name": "Book value", "columns": ["asset.assetTag", "finance.bookValueCents"], "filters": [],
        }
        result = await run_custom_report(MockTenantIsolatedDatabase(mock_db, "tenant-a"), definition, "tenant-a")
        return {row["Asset Tag"]: row for row in result["rows"]}

    @pytest.mark.asyncio
    async def test_custom_report_book_value_matches_shared_computation(self, mock_db):
        asset = _asset("a1", purchaseCostCents=250000)
        rows = await self._custom(mock_db, [asset])
        expected = compute_asset_cost(asset, MODEL, FIXED_NOW)["bookValueCents"]
        assert expected is not None
        assert rows["IT-a1"]["Book Value (cents)"] == expected

    @pytest.mark.asyncio
    async def test_custom_report_disposed_asset_shows_dash(self, mock_db):
        rows = await self._custom(mock_db, [_asset("a1", "deployed"), _asset("a2", "disposed"), _asset("a3", "retired")])
        assert rows["IT-a1"]["Book Value (cents)"] != "—"
        # The disposed and retired rows stay listed; only their book value is withheld.
        assert rows["IT-a2"]["Book Value (cents)"] == "—"
        assert rows["IT-a3"]["Book Value (cents)"] == "—"

    @pytest.mark.asyncio
    async def test_custom_report_without_policy_shows_dash(self, mock_db):
        rows = await self._custom(mock_db, [_asset("a1", modelId="model-missing")])
        assert rows["IT-a1"]["Book Value (cents)"] == "—"
