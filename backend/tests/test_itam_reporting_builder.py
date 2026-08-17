"""ITAM Custom Report Builder tests — Phase 72, Plan 03 (ITAM-REP-01).

Task 1 covers itam_reporting_filters.py's field catalogue, closed-vocabulary
FilterCondition/CustomReportDefinition validation, the Mongo fragment
builder, the shared comparison helper, and run_custom_report's asset-rooted
query + Python-side joins (including cross-tenant isolation on colliding
join keys). Task 2 extends this file with the saved custom-report routes
(save/list/preview/run/delete/export) added to itam_reporting_endpoints.py.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.itam_reporting_test_support import (  # noqa: F401 — fixtures re-exported for pytest
    MockTenantIsolatedDatabase,
    mock_db,
    patch_reporting_get_database,
    report_asset,
    report_consumable,
    report_license,
    reporting_app,
)

from itam_finance_service import compute_book_value, compute_warranty_status
from itam_reporting_filters import (
    FIELD_CATALOG,
    CustomReportDefinition,
    FilterCondition,
    _condition_passes,
    _filters_to_mongo_query,
    list_report_fields,
    run_custom_report,
)


def _cursor(rows):
    """A self-referencing MagicMock cursor whose .sort()/.limit() return the
    same cursor and whose .to_list() is the only async leaf — precedent:
    test_itam_reporting_prebuilt.py's identical helper."""
    cur = MagicMock()
    cur.sort.return_value = cur
    cur.limit.return_value = cur
    cur.to_list = AsyncMock(return_value=rows)
    return cur


def _by_tenant(rows_a, rows_b, tenant_a="tenant-a", tenant_b="tenant-b"):
    """A find() double keyed off the tenantId TenantIsolatedCollection
    injects into every query — used by the cross-tenant test below to prove
    run_custom_report never bypasses the tenant-isolated collection wrapper
    for any of its joined collection reads."""
    def _side_effect(filter_query=None, *args, **kwargs):
        tid = (filter_query or {}).get("tenantId")
        if tid == tenant_a:
            return _cursor(rows_a)
        if tid == tenant_b:
            return _cursor(rows_b)
        return _cursor([])
    return MagicMock(side_effect=_side_effect)


def _iso(days_offset: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_offset)).isoformat()


async def _run(mock_db, definition, tenant_id="tenant-a"):
    db = MockTenantIsolatedDatabase(mock_db, tenant_id)
    return await run_custom_report(db, definition, tenant_id)


# ── Field catalogue (T-72-07) ──────────────────────────────────────────────

class TestFieldCatalog:
    def test_catalog_is_non_empty_and_excludes_secret_bearing_fields(self):
        keys = [f["key"] for f in FIELD_CATALOG]
        assert len(keys) > 0
        forbidden = [k for k in keys if "productKey" in k or "customFields" in k or "tenantId" in k or k == "_id"]
        assert forbidden == []

    def test_list_report_fields_strips_source_but_keeps_key_label_entity_type(self):
        fields = list_report_fields()
        assert len(fields) == len(FIELD_CATALOG)
        for f in fields:
            assert "source" not in f
            assert set(f.keys()) == {"key", "label", "entity", "type"}


# ── FilterCondition / CustomReportDefinition validation (T-72-01) ─────────

class TestFilterConditionValidation:
    def test_unknown_field_outside_catalog_rejected(self):
        with pytest.raises(ValidationError):
            FilterCondition(field="license.productKey", operator="equals", value="x")

    def test_unknown_field_not_in_catalog_at_all_rejected(self):
        with pytest.raises(ValidationError):
            FilterCondition(field="asset.tenantId", operator="equals", value="x")

    def test_operator_outside_field_type_family_rejected(self):
        # asset.assetTag is text — gt/lt/between belong to number/date, not text.
        with pytest.raises(ValidationError):
            FilterCondition(field="asset.assetTag", operator="gt", value=1000)

    def test_unknown_operator_string_rejected_by_literal(self):
        with pytest.raises(ValidationError):
            FilterCondition(field="asset.assetTag", operator="startswith", value="x")

    def test_valid_text_condition_accepted(self):
        cond = FilterCondition(field="asset.assetTag", operator="equals", value="IT-0001")
        assert cond.field == "asset.assetTag"

    def test_valid_number_condition_accepted(self):
        cond = FilterCondition(field="asset.purchaseCostCents", operator="gt", value=1000)
        assert cond.operator == "gt"

    def test_valid_date_between_condition_accepted(self):
        cond = FilterCondition(
            field="asset.purchaseDate", operator="between", value="2026-01-01", value2="2026-02-01",
        )
        assert cond.value2 == "2026-02-01"

    def test_columns_outside_catalog_rejected(self):
        with pytest.raises(ValidationError):
            CustomReportDefinition(name="Bad Report", columns=["asset._id"], filters=[])

    def test_zero_columns_rejected(self):
        with pytest.raises(ValidationError):
            CustomReportDefinition(name="Empty Report", columns=[], filters=[])

    def test_valid_definition_accepted(self):
        definition = CustomReportDefinition(
            name="Assets by tag", columns=["asset.assetTag", "asset.name"], filters=[],
        )
        assert definition.columns == ["asset.assetTag", "asset.name"]


# ── Mongo fragment builder ──────────────────────────────────────────────────

class TestMongoFragmentBuilder:
    def test_contains_value_with_regex_metacharacters_is_escaped(self):
        cond = FilterCondition(field="asset.name", operator="contains", value="a.b*c")
        query = _filters_to_mongo_query([cond])
        pattern = query["name"]["$regex"]
        assert pattern == "a\\.b\\*c"
        # Literal match only — "." must not act as a wildcard, "*" must not
        # act as a quantifier.
        import re
        assert re.search(pattern, "prefix a.b*c suffix", re.IGNORECASE)
        assert not re.search(pattern, "prefix axbc suffix", re.IGNORECASE)

    def test_equals_produces_anchored_case_insensitive_regex(self):
        cond = FilterCondition(field="asset.assetTag", operator="equals", value="it-0001")
        query = _filters_to_mongo_query([cond])
        assert query["assetTag"]["$regex"] == "^it\\-0001$"
        assert query["assetTag"]["$options"] == "i"

    def test_between_numeric_produces_inclusive_bounds(self):
        cond = FilterCondition(field="asset.purchaseCostCents", operator="between", value=100, value2=200)
        query = _filters_to_mongo_query([cond])
        assert query["purchaseCostCents"] == {"$gte": 100, "$lte": 200}

    def test_zero_conditions_returns_empty_query(self):
        assert _filters_to_mongo_query([]) == {}

    def test_multiple_conditions_and_together(self):
        conds = [
            FilterCondition(field="asset.assetTag", operator="contains", value="IT"),
            FilterCondition(field="asset.purchaseCostCents", operator="gt", value=100),
        ]
        query = _filters_to_mongo_query(conds)
        assert "$and" in query
        assert len(query["$and"]) == 2


# ── Shared comparison helper (numeric/date boundary contract) ─────────────

class TestComparisonSemantics:
    def test_text_equals_case_insensitive_exact_and_cased_match(self):
        assert _condition_passes("text", "equals", "IT-0001", "it-0001", None) is True
        assert _condition_passes("text", "equals", "IT-0001", "IT-0001", None) is True
        assert _condition_passes("text", "equals", "IT-0001", "IT-0002", None) is False

    def test_text_contains_case_insensitive_and_literal_metacharacters(self):
        assert _condition_passes("text", "contains", "Prefix a.b*c Suffix", "a.b*c", None) is True
        assert _condition_passes("text", "contains", "Prefix axbc Suffix", "a.b*c", None) is False

    def test_numeric_gt_and_lt_are_strict(self):
        assert _condition_passes("number", "gt", 1000, 1000, None) is False
        assert _condition_passes("number", "gt", 1001, 1000, None) is True
        assert _condition_passes("number", "lt", 1000, 1000, None) is False
        assert _condition_passes("number", "lt", 999, 1000, None) is True

    def test_numeric_between_is_inclusive_both_ends(self):
        assert _condition_passes("number", "between", 100, 100, 200) is True
        assert _condition_passes("number", "between", 200, 100, 200) is True
        assert _condition_passes("number", "between", 99, 100, 200) is False
        assert _condition_passes("number", "between", 201, 100, 200) is False

    def test_between_min_equals_max_returns_exact_matches_not_empty(self):
        assert _condition_passes("number", "between", 150, 150, 150) is True
        assert _condition_passes("number", "between", 151, 150, 150) is False

    def test_date_before_after_strict(self):
        d = "2026-06-15T00:00:00+00:00"
        assert _condition_passes("date", "before", "2026-06-14T00:00:00+00:00", d, None) is True
        assert _condition_passes("date", "before", d, d, None) is False
        assert _condition_passes("date", "after", "2026-06-16T00:00:00+00:00", d, None) is True
        assert _condition_passes("date", "after", d, d, None) is False

    def test_date_between_inclusive_and_start_equals_end(self):
        start = "2026-06-01T00:00:00+00:00"
        end = "2026-06-30T00:00:00+00:00"
        assert _condition_passes("date", "between", start, start, end) is True
        assert _condition_passes("date", "between", end, start, end) is True
        assert _condition_passes("date", "between", "2026-05-31T00:00:00+00:00", start, end) is False
        # start == end: that day's rows still match, never an empty set.
        assert _condition_passes("date", "between", start, start, start) is True

    def test_missing_value_never_satisfies_any_condition(self):
        assert _condition_passes("text", "equals", None, "x", None) is False
        assert _condition_passes("number", "gt", None, 0, None) is False


# ── run_custom_report: end-to-end behavior over the asset-rooted query ────

class TestRunCustomReportBehavior:
    @pytest.mark.asyncio
    async def test_zero_filters_returns_every_in_scope_row(self, mock_db):
        assets = [
            report_asset(id="a1", assetTag="IT-0002", name="Second"),
            report_asset(id="a2", assetTag="IT-0001", name="First"),
        ]
        mock_db.assets.find.return_value.to_list.return_value = assets
        mock_db.license_assignments.find.return_value.to_list.return_value = []
        mock_db.components.find.return_value.to_list.return_value = []
        mock_db.itam_consumables.find.return_value.to_list.return_value = []
        mock_db.asset_models.find.return_value.to_list.return_value = []
        mock_db.system_settings.find_one = AsyncMock(return_value=None)

        definition = {"name": "All assets", "columns": ["asset.assetTag"], "filters": []}
        result = await _run(mock_db, definition)

        assert result["rowCount"] == 2
        assert {r["Asset Tag"] for r in result["rows"]} == {"IT-0001", "IT-0002"}

    @pytest.mark.asyncio
    async def test_default_sort_is_asset_tag_ascending_and_repeatable(self, mock_db):
        assets = [
            report_asset(id="a1", assetTag="IT-0003"),
            report_asset(id="a2", assetTag="IT-0001"),
            report_asset(id="a3", assetTag="IT-0002"),
        ]
        mock_db.assets.find.return_value.to_list.return_value = assets
        mock_db.license_assignments.find.return_value.to_list.return_value = []
        mock_db.components.find.return_value.to_list.return_value = []
        mock_db.itam_consumables.find.return_value.to_list.return_value = []
        mock_db.asset_models.find.return_value.to_list.return_value = []
        mock_db.system_settings.find_one = AsyncMock(return_value=None)

        definition = {"name": "Sorted", "columns": ["asset.assetTag"], "filters": []}
        result_1 = await _run(mock_db, definition)
        result_2 = await _run(mock_db, definition)

        expected = ["IT-0001", "IT-0002", "IT-0003"]
        assert [r["Asset Tag"] for r in result_1["rows"]] == expected
        assert [r["Asset Tag"] for r in result_2["rows"]] == expected

    @pytest.mark.asyncio
    async def test_numeric_gt_and_between_boundaries_via_full_report(self, mock_db):
        assets = [
            report_asset(id="a1", assetTag="IT-0001", purchaseCostCents=1000),
            report_asset(id="a2", assetTag="IT-0002", purchaseCostCents=1001),
            report_asset(id="a3", assetTag="IT-0003", purchaseCostCents=100),
            report_asset(id="a4", assetTag="IT-0004", purchaseCostCents=200),
        ]
        mock_db.assets.find.return_value.to_list.return_value = assets
        mock_db.license_assignments.find.return_value.to_list.return_value = []
        mock_db.components.find.return_value.to_list.return_value = []
        mock_db.itam_consumables.find.return_value.to_list.return_value = []
        mock_db.asset_models.find.return_value.to_list.return_value = []
        mock_db.system_settings.find_one = AsyncMock(return_value=None)

        gt_definition = {
            "name": "Cost gt 1000",
            "columns": ["asset.assetTag"],
            "filters": [{"field": "asset.purchaseCostCents", "operator": "gt", "value": 1000}],
        }
        gt_result = await _run(mock_db, gt_definition)
        assert [r["Asset Tag"] for r in gt_result["rows"]] == ["IT-0002"]

        between_definition = {
            "name": "Cost between 100 and 200",
            "columns": ["asset.assetTag"],
            "filters": [{"field": "asset.purchaseCostCents", "operator": "between", "value": 100, "value2": 200}],
        }
        between_result = await _run(mock_db, between_definition)
        assert {r["Asset Tag"] for r in between_result["rows"]} == {"IT-0003", "IT-0004"}

    @pytest.mark.asyncio
    async def test_finance_bookvalue_column_matches_compute_book_value_verbatim(self, mock_db):
        model = {"id": "model-1", "usefulLifeYears": 5, "salvageValueCents": 10000}
        purchase_date = _iso(400)
        asset = report_asset(
            id="a1", assetTag="IT-0001", modelId="model-1",
            purchaseCostCents=250000, purchaseDate=purchase_date,
        )
        mock_db.assets.find.return_value.to_list.return_value = [asset]
        mock_db.license_assignments.find.return_value.to_list.return_value = []
        mock_db.components.find.return_value.to_list.return_value = []
        mock_db.itam_consumables.find.return_value.to_list.return_value = []
        mock_db.asset_models.find.return_value.to_list.return_value = [model]
        mock_db.system_settings.find_one = AsyncMock(return_value=None)

        definition = {"name": "Book value", "columns": ["asset.assetTag", "finance.bookValueCents"], "filters": []}
        result = await _run(mock_db, definition)

        expected = compute_book_value(
            purchase_date=purchase_date, purchase_cost_cents=250000,
            useful_life_years=5, salvage_value_cents=10000, now=datetime.now(timezone.utc),
        )
        assert result["rows"][0]["Book Value (cents)"] == expected["bookValueCents"]

    @pytest.mark.asyncio
    async def test_license_join_populates_column_from_assignment_and_license_docs(self, mock_db):
        asset = report_asset(id="a1", assetTag="IT-0001")
        assignment = {"id": "la-1", "licenseId": "lic-1", "targetType": "asset", "targetId": "a1"}
        lic = report_license(id="lic-1", name="Acme Suite", seatCount=10)
        mock_db.assets.find.return_value.to_list.return_value = [asset]
        mock_db.license_assignments.find.return_value.to_list.return_value = [assignment]
        mock_db.licenses.find.return_value.to_list.return_value = [lic]
        mock_db.components.find.return_value.to_list.return_value = []
        mock_db.itam_consumables.find.return_value.to_list.return_value = []
        mock_db.asset_models.find.return_value.to_list.return_value = []
        mock_db.system_settings.find_one = AsyncMock(return_value=None)

        definition = {"name": "License join", "columns": ["asset.assetTag", "license.name"], "filters": []}
        result = await _run(mock_db, definition)

        assert result["rows"][0]["License"] == "Acme Suite"

    @pytest.mark.asyncio
    async def test_component_join_populates_column_via_parent_asset_id(self, mock_db):
        asset = report_asset(id="a1", assetTag="IT-0001")
        component = {"id": "comp-1", "name": "16GB RAM", "type": "ram", "parentAssetId": "a1"}
        mock_db.assets.find.return_value.to_list.return_value = [asset]
        mock_db.license_assignments.find.return_value.to_list.return_value = []
        mock_db.components.find.return_value.to_list.return_value = [component]
        mock_db.itam_consumables.find.return_value.to_list.return_value = []
        mock_db.asset_models.find.return_value.to_list.return_value = []
        mock_db.system_settings.find_one = AsyncMock(return_value=None)

        definition = {"name": "Component join", "columns": ["asset.assetTag", "component.name"], "filters": []}
        result = await _run(mock_db, definition)

        assert result["rows"][0]["Component"] == "16GB RAM"

    @pytest.mark.asyncio
    async def test_consumable_join_populates_column_from_checkout_records(self, mock_db):
        asset = report_asset(id="a1", assetTag="IT-0001")
        consumable = report_consumable(
            id="con-1", name="USB-C Cable",
            checkoutRecords=[{"assignedTo": "a1", "assignedToType": "asset", "quantity": 2}],
        )
        mock_db.assets.find.return_value.to_list.return_value = [asset]
        mock_db.license_assignments.find.return_value.to_list.return_value = []
        mock_db.components.find.return_value.to_list.return_value = []
        mock_db.itam_consumables.find.return_value.to_list.return_value = [consumable]
        mock_db.asset_models.find.return_value.to_list.return_value = []
        mock_db.system_settings.find_one = AsyncMock(return_value=None)

        definition = {
            "name": "Consumable join",
            "columns": ["asset.assetTag", "consumable.name", "consumable.checkedOutQuantity"],
            "filters": [],
        }
        result = await _run(mock_db, definition)

        assert result["rows"][0]["Consumable"] == "USB-C Cable"
        assert result["rows"][0]["Checked-Out Quantity"] == 2

    @pytest.mark.asyncio
    async def test_missing_value_renders_as_em_dash_not_none_or_blank(self, mock_db):
        asset = report_asset(id="a1", assetTag="IT-0001", notes=None)
        mock_db.assets.find.return_value.to_list.return_value = [asset]
        mock_db.license_assignments.find.return_value.to_list.return_value = []
        mock_db.components.find.return_value.to_list.return_value = []
        mock_db.itam_consumables.find.return_value.to_list.return_value = []
        mock_db.asset_models.find.return_value.to_list.return_value = []
        mock_db.system_settings.find_one = AsyncMock(return_value=None)

        definition = {"name": "Notes", "columns": ["asset.assetTag", "asset.notes"], "filters": []}
        result = await _run(mock_db, definition)

        assert result["rows"][0]["Notes"] == "—"

    @pytest.mark.asyncio
    async def test_zero_rows_still_returns_declared_columns(self, mock_db):
        mock_db.assets.find.return_value.to_list.return_value = []
        mock_db.license_assignments.find.return_value.to_list.return_value = []
        mock_db.components.find.return_value.to_list.return_value = []
        mock_db.itam_consumables.find.return_value.to_list.return_value = []
        mock_db.asset_models.find.return_value.to_list.return_value = []
        mock_db.system_settings.find_one = AsyncMock(return_value=None)

        definition = {"name": "Empty", "columns": ["asset.assetTag", "asset.name"], "filters": []}
        result = await _run(mock_db, definition)

        assert result["rows"] == []
        assert result["columns"] == ["Asset Tag", "Name"]


class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_tenant_isolation_across_colliding_join_keys(self, mock_db):
        """Two tenants share an assetId and a licenceId — a real-world id
        collision. Running the report as tenant-a must never surface
        tenant-b's licence name or asset tag, proving run_custom_report
        never bypasses the tenant-isolated collection wrapper for any of its
        joined collection reads (T-72-02)."""
        asset_a = report_asset(id="asset-1", tenantId="tenant-a", assetTag="IT-A1", modelId="model-shared")
        asset_b = report_asset(id="asset-1", tenantId="tenant-b", assetTag="IT-B1", modelId="model-shared")

        assign_a = {"id": "la-1", "tenantId": "tenant-a", "licenseId": "lic-shared", "targetType": "asset", "targetId": "asset-1"}
        assign_b = {"id": "la-1", "tenantId": "tenant-b", "licenseId": "lic-shared", "targetType": "asset", "targetId": "asset-1"}

        lic_a = report_license(id="lic-shared", tenantId="tenant-a", name="Tenant A Suite")
        lic_b = report_license(id="lic-shared", tenantId="tenant-b", name="Tenant B SECRET Suite")

        mock_db.assets.find = _by_tenant([asset_a], [asset_b])
        mock_db.license_assignments.find = _by_tenant([assign_a], [assign_b])
        mock_db.licenses.find = _by_tenant([lic_a], [lic_b])
        mock_db.components.find = _by_tenant([], [])
        mock_db.itam_consumables.find = _by_tenant([], [])
        mock_db.asset_models.find = _by_tenant([], [])
        mock_db.system_settings.find_one = AsyncMock(return_value=None)

        definition = {
            "name": "Cross-tenant probe",
            "columns": ["asset.assetTag", "license.name"],
            "filters": [],
        }
        result = await _run(mock_db, definition, tenant_id="tenant-a")

        serialized = repr(result)
        assert "Tenant B SECRET Suite" not in serialized
        assert "IT-B1" not in serialized
        assert result["rows"][0]["Asset Tag"] == "IT-A1"
        assert result["rows"][0]["License"] == "Tenant A Suite"
