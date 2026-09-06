"""ITAM dashboard KPI aggregation tests — Phase 72, Plan 04 (ITAM-REP-04).

Task 1: `compute_itam_kpis` — the four tenant-scoped aggregates. One test
class per KPI plus the cross-cutting no-data and tenant-isolation behaviors.
Task 2 (route-level tests) is appended below by that task.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.conftest import make_test_app, make_token_data
from tests.itam_reporting_test_support import (  # noqa: F401 — fixtures re-exported for pytest
    mock_db,
    MockTenantIsolatedDatabase,
    report_asset,
    report_license,
)

from authentication_service import get_current_user as real_get_current_user
from api_key_auth import get_current_user_or_api_key  # Phase 73 (D-01/D-02): routes gated by _require_itam_admin now resolve through this dependency, not get_current_user
import itam_asset_endpoints
import itam_kpi_endpoints
from itam_finance_service import compute_book_value
from itam_models import LifecycleStatus
from itam_reporting_kpis import compute_itam_kpis
from itam_reporting_prebuilt import PREBUILT_REPORTS


def _seed_defaults(mock_db):
    """Every test overrides only what it needs on top of this baseline —
    empty assets/licenses, a real (30-day default) warranty window, and
    count_documents mocks (conftest._make_col does not configure these —
    only find/find_one/update_one/delete_one/find/distinct/aggregate)."""
    mock_db.assets.find.return_value.to_list.return_value = []
    mock_db.licenses.find.return_value.to_list.return_value = []
    mock_db.asset_models.find.return_value.to_list.return_value = []
    mock_db.system_settings.find_one = AsyncMock(return_value=None)
    mock_db.assets.count_documents = AsyncMock(return_value=0)
    mock_db.license_assignments.count_documents = AsyncMock(return_value=0)


class TestAssetValueKpi:
    @pytest.mark.asyncio
    async def test_status_breakdown_sequence_matches_enum_order_including_zero_counts(self, mock_db):
        _seed_defaults(mock_db)
        deployed = report_asset(id="a1", lifecycleStatus="deployed")
        retired = report_asset(id="a2", lifecycleStatus="retired")
        no_status_key = report_asset(id="a3")
        del no_status_key["lifecycleStatus"]  # genuinely absent, not just falsy
        mock_db.assets.find.return_value.to_list.return_value = [deployed, retired, no_status_key]

        wrapped = MockTenantIsolatedDatabase(mock_db, "tenant-a")
        result = await compute_itam_kpis(wrapped, "tenant-a")

        breakdown = result["assetValue"]["statusBreakdown"]
        assert [seg["status"] for seg in breakdown] == [s.value for s in LifecycleStatus]
        counts = {seg["status"]: seg["count"] for seg in breakdown}
        assert counts["deployed"] == 1
        assert counts["retired"] == 1
        assert counts["deployable"] == 1  # the asset with no lifecycleStatus key
        assert counts["archived"] == 0
        assert counts["disposed"] == 0
        assert counts["broken"] == 0

    @pytest.mark.asyncio
    async def test_total_book_value_equals_direct_compute_book_value_sum(self, mock_db):
        _seed_defaults(mock_db)
        now = datetime.now(timezone.utc)
        purchase_date = (now - timedelta(days=400)).isoformat()

        with_policy = report_asset(
            id="a1", modelId="model-1", purchaseCostCents=120000, purchaseDate=purchase_date,
        )
        without_matching_model = report_asset(
            id="a2", modelId="model-missing", purchaseCostCents=50000, purchaseDate=purchase_date,
        )
        no_purchase_record = report_asset(id="a3", purchaseCostCents=None, purchaseDate=None)
        mock_db.assets.find.return_value.to_list.return_value = [
            with_policy, without_matching_model, no_purchase_record,
        ]
        mock_db.asset_models.find.return_value.to_list.return_value = [
            {"id": "model-1", "usefulLifeYears": 3, "salvageValueCents": 10000},
        ]

        wrapped = MockTenantIsolatedDatabase(mock_db, "tenant-a")
        result = await compute_itam_kpis(wrapped, "tenant-a")

        expected = compute_book_value(
            purchase_date=purchase_date, purchase_cost_cents=120000,
            useful_life_years=3, salvage_value_cents=10000, now=now,
        )
        asset_value = result["assetValue"]
        assert asset_value["hasData"] is True
        assert asset_value["totalBookValueCents"] == expected["bookValueCents"]
        assert asset_value["assetCount"] == 3
        # without_matching_model (no depreciation policy) + no_purchase_record
        # (no purchase record at all) both contribute nothing to the sum.
        assert asset_value["withoutPolicyCount"] == 2
        assert asset_value["drilldownReportKey"] == "asset_value"

    @pytest.mark.asyncio
    async def test_asset_with_valueerror_inputs_counted_without_policy_not_failed(self, mock_db):
        _seed_defaults(mock_db)
        # useful_life_years=0 makes compute_book_value raise ValueError.
        bad_policy_asset = report_asset(
            id="a1", modelId="model-1", purchaseCostCents=100000, purchaseDate="2024-01-01T00:00:00+00:00",
        )
        mock_db.assets.find.return_value.to_list.return_value = [bad_policy_asset]
        mock_db.asset_models.find.return_value.to_list.return_value = [
            {"id": "model-1", "usefulLifeYears": 0, "salvageValueCents": 1000},
        ]

        wrapped = MockTenantIsolatedDatabase(mock_db, "tenant-a")
        result = await compute_itam_kpis(wrapped, "tenant-a")

        asset_value = result["assetValue"]
        assert asset_value["totalBookValueCents"] == 0
        assert asset_value["withoutPolicyCount"] == 1


class TestLicenseUtilizationKpi:
    @pytest.mark.asyncio
    async def test_utilization_percent_and_seat_math(self, mock_db):
        _seed_defaults(mock_db)
        lic1 = report_license(id="lic-1", seatCount=10)
        lic2 = report_license(id="lic-2", seatCount=5)
        mock_db.licenses.find.return_value.to_list.return_value = [lic1, lic2]
        mock_db.license_assignments.count_documents = AsyncMock(side_effect=[4, 3])

        wrapped = MockTenantIsolatedDatabase(mock_db, "tenant-a")
        result = await compute_itam_kpis(wrapped, "tenant-a")

        lic = result["licenseUtilization"]
        assert lic["hasData"] is True
        assert lic["seatsTotal"] == 15
        assert lic["seatsAssigned"] == 7
        assert lic["seatsAvailable"] == 8
        assert lic["utilizationPercent"] == round(7 / 15 * 100, 1)
        assert lic["drilldownReportKey"] == "license_utilization"

    @pytest.mark.asyncio
    async def test_zero_total_seats_reports_no_data_not_a_percentage(self, mock_db):
        _seed_defaults(mock_db)
        lic = report_license(id="lic-1", seatCount=0)
        mock_db.licenses.find.return_value.to_list.return_value = [lic]
        mock_db.license_assignments.count_documents = AsyncMock(return_value=0)

        wrapped = MockTenantIsolatedDatabase(mock_db, "tenant-a")
        result = await compute_itam_kpis(wrapped, "tenant-a")

        lic_kpi = result["licenseUtilization"]
        assert lic_kpi["hasData"] is False
        assert lic_kpi["utilizationPercent"] is None


class TestWarrantyExpirationsKpi:
    @pytest.mark.asyncio
    async def test_expiring_soon_boundary_is_inclusive(self, mock_db):
        _seed_defaults(mock_db)
        # 0 warrantyMonths is a no-op for _add_months, so warrantyExpiresAt
        # lands exactly `days` from purchaseDate — sidesteps calendar-month
        # arithmetic for a precise boundary value.
        purchase_date = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        asset = report_asset(id="a1", purchaseDate=purchase_date, warrantyMonths=0)
        mock_db.assets.find.return_value.to_list.return_value = [asset]

        wrapped = MockTenantIsolatedDatabase(mock_db, "tenant-a")
        result = await compute_itam_kpis(wrapped, "tenant-a")

        warranty = result["warrantyExpirations"]
        assert warranty["hasData"] is True
        assert warranty["alertWindowDays"] == 30
        assert warranty["expiringSoonCount"] == 1
        assert warranty["drilldownReportKey"] == "warranty_expiring"

    @pytest.mark.asyncio
    async def test_timeline_covers_next_twelve_months_and_excludes_already_expired(self, mock_db):
        _seed_defaults(mock_db)
        now = datetime.now(timezone.utc)
        upcoming_1 = report_asset(id="a1", purchaseDate=(now + timedelta(days=70)).isoformat(), warrantyMonths=0)
        upcoming_2 = report_asset(id="a2", purchaseDate=(now + timedelta(days=160)).isoformat(), warrantyMonths=0)
        already_expired = report_asset(id="a3", purchaseDate=(now - timedelta(days=10)).isoformat(), warrantyMonths=0)
        mock_db.assets.find.return_value.to_list.return_value = [upcoming_1, upcoming_2, already_expired]

        wrapped = MockTenantIsolatedDatabase(mock_db, "tenant-a")
        result = await compute_itam_kpis(wrapped, "tenant-a")

        warranty = result["warrantyExpirations"]
        timeline = warranty["timeline"]
        assert len(timeline) == 12
        assert sum(entry["count"] for entry in timeline) == 2  # only the two future expiries
        assert warranty["expiredCount"] == 1

    @pytest.mark.asyncio
    async def test_no_data_when_no_asset_has_both_purchase_date_and_warranty_length(self, mock_db):
        _seed_defaults(mock_db)
        no_warranty = report_asset(id="a1", purchaseDate="2024-01-01T00:00:00+00:00", warrantyMonths=None)
        mock_db.assets.find.return_value.to_list.return_value = [no_warranty]

        wrapped = MockTenantIsolatedDatabase(mock_db, "tenant-a")
        result = await compute_itam_kpis(wrapped, "tenant-a")

        warranty = result["warrantyExpirations"]
        assert warranty["hasData"] is False
        assert warranty["expiringSoonCount"] is None
        assert warranty["timeline"] == []


class TestOverdueKpi:
    @staticmethod
    def _overdue_find_side_effect(audit_ids, checkin_ids, batch_assets):
        """`_compute_overdue_kpi` issues two `db.assets.find(...).to_list()`
        calls distinguishable by filter shape: the audit-overdue query is the
        `_overdue_query` `$or` population, the checkin-overdue query filters
        on `expectedReturnDate`. The one batched top-level `find({}, ...)` in
        `compute_itam_kpis` (empty filter) falls through to `batch_assets`."""
        def _side_effect(query, *args, **kwargs):
            if "expectedReturnDate" in query:
                docs = [{"id": i} for i in checkin_ids]
            elif "$or" in query:
                docs = [{"id": i} for i in audit_ids]
            else:
                docs = batch_assets
            return MagicMock(to_list=AsyncMock(return_value=docs))
        return _side_effect

    @pytest.mark.asyncio
    async def test_audit_and_checkin_counts_separate_and_summed(self, mock_db):
        _seed_defaults(mock_db)
        mock_db.assets.find = MagicMock(side_effect=self._overdue_find_side_effect(
            audit_ids=["au1", "au2"], checkin_ids=["c1", "c2", "c3"],
            batch_assets=[report_asset(id="a1")],
        ))

        wrapped = MockTenantIsolatedDatabase(mock_db, "tenant-a")
        result = await compute_itam_kpis(wrapped, "tenant-a")

        overdue = result["overdue"]
        assert overdue["hasData"] is True
        assert overdue["overdueAuditCount"] == 2
        assert overdue["overdueCheckinCount"] == 3
        assert overdue["totalCount"] == 5
        assert overdue["drilldownReportKey"] == "overdue_audits"

    @pytest.mark.asyncio
    async def test_asset_overdue_on_both_axes_is_not_double_counted(self, mock_db):
        """WR-02 regression test: an asset overdue on both the audit and
        checkin axes must be counted once in totalCount, not twice."""
        _seed_defaults(mock_db)
        mock_db.assets.find = MagicMock(side_effect=self._overdue_find_side_effect(
            audit_ids=["shared", "au2"], checkin_ids=["shared", "c2"],
            batch_assets=[report_asset(id="a1")],
        ))

        wrapped = MockTenantIsolatedDatabase(mock_db, "tenant-a")
        result = await compute_itam_kpis(wrapped, "tenant-a")

        overdue = result["overdue"]
        assert overdue["overdueAuditCount"] == 2
        assert overdue["overdueCheckinCount"] == 2
        assert overdue["totalCount"] == 3  # "shared" counted once, not twice


class TestNoDataAndDrilldownKeys:
    @pytest.mark.asyncio
    async def test_every_kpi_reports_no_data_on_empty_tenant_never_a_fabricated_number(self, mock_db):
        _seed_defaults(mock_db)

        wrapped = MockTenantIsolatedDatabase(mock_db, "tenant-a")
        result = await compute_itam_kpis(wrapped, "tenant-a")

        for key in ("assetValue", "licenseUtilization", "warrantyExpirations", "overdue"):
            assert result[key]["hasData"] is False, key
            assert result[key]["drilldownReportKey"] in PREBUILT_REPORTS

        assert result["licenseUtilization"]["utilizationPercent"] is None
        assert result["licenseUtilization"]["seatsAssigned"] is None
        assert result["overdue"]["overdueAuditCount"] is None
        assert result["overdue"]["overdueCheckinCount"] is None
        assert result["warrantyExpirations"]["expiringSoonCount"] is None
        assert result["assetValue"]["totalBookValueCents"] is None


# ---------------------------------------------------------------------------
# Cross-tenant isolation — a lightweight real-filtering fake db.
#
# The shared mock_db fixture's `.find.return_value` is a fixed value
# regardless of the query, which can't distinguish "tenant-a data" from
# "tenant-b data" the way a real db would. This fake implements just enough
# real filtering (matched against the tenantId term MockTenantIsolatedDatabase
# auto-injects) to prove a second tenant's data never contributes to the
# first tenant's numbers.
# ---------------------------------------------------------------------------

def _matches(doc, filt):
    for key, expected in filt.items():
        if key == "$or":
            if not any(_matches(doc, clause) for clause in expected):
                return False
            continue
        if isinstance(expected, dict):
            if "$in" in expected and doc.get(key) not in expected["$in"]:
                return False
            if "$ne" in expected and doc.get(key) == expected["$ne"]:
                return False
            if "$lt" in expected and not (doc.get(key) is not None and doc.get(key) < expected["$lt"]):
                return False
            if "$exists" in expected and (key in doc) != expected["$exists"]:
                return False
            continue
        if doc.get(key) != expected:
            return False
    return True


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, length=None):
        return list(self._docs)


class _FakeCollection:
    def __init__(self, docs):
        self._docs = docs  # shared, mutable list reference with the owning db

    def find(self, filt=None, projection=None):
        return _FakeCursor([d for d in self._docs if _matches(d, filt or {})])

    async def count_documents(self, filt=None):
        return len([d for d in self._docs if _matches(d, filt or {})])


class _NullSystemSettings:
    async def find_one(self, query):
        return None


class _FakeKpiDb:
    """Raw (unwrapped) db — wrapped by MockTenantIsolatedDatabase in the test
    below so every read is auto-scoped by tenantId exactly like production's
    TenantIsolatedDatabase."""

    def __init__(self):
        self._assets = []
        self._licenses = []
        self._license_assignments = []
        self._asset_models = []
        self.assets = _FakeCollection(self._assets)
        self.licenses = _FakeCollection(self._licenses)
        self.license_assignments = _FakeCollection(self._license_assignments)
        self.asset_models = _FakeCollection(self._asset_models)
        self.system_settings = _NullSystemSettings()


class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_seeding_a_second_tenant_does_not_change_the_first_tenants_kpis(self):
        raw_db = _FakeKpiDb()
        raw_db._assets.append(report_asset(
            id="a1", tenantId="tenant-a", purchaseCostCents=100000,
            purchaseDate="2024-01-01T00:00:00+00:00",
        ))
        raw_db._licenses.append(report_license(id="lic-a", tenantId="tenant-a", seatCount=10))
        raw_db._license_assignments.append({"id": "la-1", "tenantId": "tenant-a", "licenseId": "lic-a"})

        wrapped_a = MockTenantIsolatedDatabase(raw_db, "tenant-a")
        before = await compute_itam_kpis(wrapped_a, "tenant-a")

        # Seed a second, unrelated tenant's data directly into the same
        # underlying collections.
        raw_db._assets.append(report_asset(
            id="b1", tenantId="tenant-b", purchaseCostCents=999999,
            purchaseDate="2020-01-01T00:00:00+00:00", lifecycleStatus="deployed",
        ))
        raw_db._licenses.append(report_license(id="lic-b", tenantId="tenant-b", seatCount=50))
        raw_db._license_assignments.append({"id": "la-2", "tenantId": "tenant-b", "licenseId": "lic-b"})

        after = await compute_itam_kpis(wrapped_a, "tenant-a")

        assert after == before


# ---------------------------------------------------------------------------
# Task 2: GET /api/itam/kpis route-level tests.
# ---------------------------------------------------------------------------

def _kpi_client(app, tenant_id="tenant-a", role="admin", username="admin@example.com"):
    current_user = make_token_data(tenant_id=tenant_id, role=role, username=username)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: current_user
    app.dependency_overrides[real_get_current_user] = lambda: current_user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


def _make_kpi_app(mock_db, monkeypatch, permission_ok=True):
    """Builds a test app mounting only itam_kpi_endpoints.router. Patches
    get_database at itam_kpi_endpoints' own bound name (name-binding import)
    and verify_permission at itam_asset_endpoints' own bound name — the RBAC
    dependency _require_itam_admin imports from there."""
    def get_mock_tenant_db():
        return MockTenantIsolatedDatabase(mock_db, "tenant-a")

    monkeypatch.setattr(itam_kpi_endpoints, "get_database", get_mock_tenant_db)
    monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=permission_ok))
    app, _ = make_test_app(itam_kpi_endpoints.router)
    return app


class TestItamKpiRoute:
    @pytest.mark.asyncio
    async def test_get_kpis_returns_200_with_four_kpi_keys(self, mock_db, monkeypatch):
        _seed_defaults(mock_db)
        app = _make_kpi_app(mock_db, monkeypatch)

        async with _kpi_client(app) as ac:
            r = await ac.get("/api/itam/kpis")

        assert r.status_code == 200, r.text
        body = r.json()
        assert set(body.keys()) == {"assetValue", "licenseUtilization", "warrantyExpirations", "overdue"}

    @pytest.mark.asyncio
    async def test_get_kpis_returns_403_when_permission_check_fails(self, mock_db, monkeypatch):
        _seed_defaults(mock_db)
        app = _make_kpi_app(mock_db, monkeypatch, permission_ok=False)

        async with _kpi_client(app) as ac:
            r = await ac.get("/api/itam/kpis")

        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_get_kpis_returns_403_when_no_tenant_id(self, mock_db, monkeypatch):
        _seed_defaults(mock_db)
        app = _make_kpi_app(mock_db, monkeypatch)

        async with _kpi_client(app, tenant_id=None) as ac:
            r = await ac.get("/api/itam/kpis")

        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_get_kpis_returns_500_with_generic_detail_on_backend_exception(self, mock_db, monkeypatch):
        _seed_defaults(mock_db)
        app = _make_kpi_app(mock_db, monkeypatch)

        async def _boom(db, tenant_id):
            raise RuntimeError("boom - internal detail that must not leak")

        monkeypatch.setattr(itam_kpi_endpoints, "compute_itam_kpis", _boom)

        async with _kpi_client(app) as ac:
            r = await ac.get("/api/itam/kpis")

        assert r.status_code == 500
        assert r.json()["detail"] == "Internal server error"
        assert "boom" not in r.text
