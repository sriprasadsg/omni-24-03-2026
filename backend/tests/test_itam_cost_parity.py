"""Cost parity across every ITAM money surface - Phase 78 Plan 08, Task 1 (SC3; COST-01, 02, 03, 06).

One seeded tenant (tenant-p) that covers every D-01..D-12 case, with a second tenant (tenant-q)
holding overlapping tags, names, model ids and a same-serial pair as noise, in a real throwaway
MongoDB behind the production TenantIsolatedDatabase wrapper. Over one patched
itam_cost_service.utc_now the KPI tile, the Asset value report, the cost summary and the cost list
must show the same integers, and the per-asset book-value route must agree with the list row.

Expected figures come from compute_book_value (the Phase 59 depreciation) at the fixed clock,
never from the implementation under test. Report money cells are parsed with Decimal.
"""
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests._mongo_test_db import mongo_db  # noqa: F401 - fixture re-exported for pytest
from tests.conftest import make_token_data

import database
import itam_cost_service
import itam_finance_endpoints
import tenant_context
from itam_cost_service import compute_tenant_costs
from itam_finance_service import compute_book_value
from itam_reporting_kpis import compute_itam_kpis
from itam_reporting_prebuilt import run_prebuilt_report

FIXED = datetime.now(timezone.utc)  # the real now, captured once; every surface reads it through utc_now
INACTIVE = ("disposed", "retired")
MODELS = {  # the depreciation policy of tenant-p; model "model-b" has no salvage so a $0 price stays 0
    "model-ok": (3, 10000),
    "model-b": (5, 0),
    "model-hi": (3, 150000),  # salvage above the price paid for N-SALVAGE: that asset is not valued (IN-03)
}
UNSET = object()


def _when(days_ago):
    return (FIXED - timedelta(days=days_ago)).isoformat()


# tag, lifecycleStatus (UNSET = key absent), cost, purchase date, model id
SPEC = [
    ("V-DEPLOYED", "deployed", 120000, _when(50), "model-ok"),
    ("V-DEPLOYABLE", "deployable", 80000, _when(200), "model-ok"),
    ("V-ARCHIVED", "archived", 150000, _when(500), "model-b"),
    ("V-BROKEN", "broken", 60000, _when(900), "model-ok"),
    ("V-NOSTATUS", UNSET, 40000, _when(1300), "model-b"),
    ("X-DISPOSED", "disposed", 90000, _when(200), "model-ok"),
    ("X-RETIRED", "retired", 70000, _when(500), "model-ok"),
    ("N-NOMODEL", "deployed", 30000, _when(200), "model-gone"),
    ("N-HAND", "deployed", 55000, _when(200), "model-ok"),
    ("N-MALCOST", "deployed", "1000", _when(200), "model-ok"),
    ("N-BADDATE", "deployed", 45000, "31/12/2020", "model-ok"),
    ("N-FUTURE", "deployed", 25000, (FIXED + timedelta(days=400)).isoformat(), "model-ok"),
    ("N-ZERO", "deployed", 0, _when(200), "model-b"),
    ("N-AGENT", "deployed", None, None, None),
    ("N-SALVAGE", "deployed", 100000, _when(200), "model-hi"),
]
NOT_TRACKED = {
    "N-AGENT": "no_purchase_record",
    "N-NOMODEL": "no_depreciation_policy_assigned",
    "N-MALCOST": "unreadable_purchase_cost",
    "N-BADDATE": "unreadable_purchase_date",
    "N-SALVAGE": "salvage_exceeds_cost",
}


def _doc(tenant, tag, status, cost, date, model):
    doc = {"tenantId": tenant, "id": f"{tenant}:{tag}", "assetTag": tag, "name": f"Laptop {tag}"}
    if status is not UNSET:
        doc["lifecycleStatus"] = status
    for key, value in (("purchaseCostCents", cost), ("purchaseDate", date), ("modelId", model)):
        if value is not None:
            doc[key] = value
    if tag == "N-AGENT":
        doc["hardwareKey"] = "serial:XYZ789"
    if tag == "N-HAND":
        doc["serialNumber"] = "xyz789"
    return doc


def _expected_book_values():
    """tag -> book value cents for every in-scope asset the depreciation can value."""
    expected = {}
    for tag, status, cost, date, model in SPEC:
        if status in INACTIVE or not isinstance(cost, int) or model not in MODELS:
            continue
        try:
            life, salvage = MODELS[model]
            if salvage > cost:
                continue  # salvage above the price paid: not valued, nothing capped
            expected[tag] = compute_book_value(date, cost, life, salvage, FIXED)["bookValueCents"]
        except ValueError:
            continue  # the unparseable date
    return expected


def _active_tags():
    return [s[0] for s in SPEC if s[1] not in INACTIVE]


def _cost_of(tag):
    return next(s[2] for s in SPEC if s[0] == tag)


@contextmanager
def _as_tenant(tenant_id):
    token = tenant_context.set_tenant_id(tenant_id)
    try:
        yield
    finally:
        tenant_context.reset_tenant_id(token)


@pytest_asyncio.fixture
async def seeded(mongo_db, monkeypatch):
    monkeypatch.setattr(itam_cost_service, "utc_now", lambda: FIXED)
    await mongo_db.asset_models.insert_many(
        [{"tenantId": "tenant-p", "id": m, "usefulLifeYears": life, "salvageValueCents": salvage}
         for m, (life, salvage) in MODELS.items()]
        + [{"tenantId": "tenant-q", "id": "model-ok", "usefulLifeYears": 1, "salvageValueCents": 0}]
    )
    await mongo_db.assets.insert_many(
        [_doc("tenant-p", *spec) for spec in SPEC]
        + [_doc("tenant-q", tag, "deployed", 999000, _when(100), "model-ok")
           for tag in ("V-DEPLOYED", "N-HAND", "X-DISPOSED", "N-AGENT")]
    )
    await mongo_db.agents.insert_many([
        {"tenantId": "tenant-p", "id": "agent-p1", "assetId": "tenant-p:N-AGENT", "hostname": "p-host",
         "status": "Online", "lastSeen": "2026-11-16T10:00:00Z"},
        {"tenantId": "tenant-q", "id": "agent-q1", "assetId": "tenant-q:N-AGENT", "hostname": "q-host",
         "status": "Online", "lastSeen": "2026-11-16T10:00:00Z"},
    ])
    return mongo_db


def _cents(cell):
    """A report money cell such as "$1,234.56" as integer cents; the em dash means no value."""
    if cell == "—":
        return None
    return int((Decimal(cell.replace("$", "").replace(",", "")) * 100).to_integral_exact())


async def _surfaces(raw_db):
    """All four surfaces for tenant-p over one wrapped database handle."""
    db = database.TenantIsolatedDatabase(raw_db)
    with _as_tenant("tenant-p"):
        kpi = await compute_itam_kpis(db, "tenant-p")
        report = await run_prebuilt_report(db, "asset_value", "tenant-p")
        costs = await compute_tenant_costs(db, "tenant-p", with_agents=True)
        with_inactive = await compute_tenant_costs(db, "tenant-p", include_inactive=True, with_agents=True)
    return {"kpi": kpi, "report": report, "costs": costs, "with_inactive": with_inactive}


def _rows_by_tag(result):
    return {row["assetTag"]: row for row in result["rows"]}


class TestParity:
    @pytest.mark.asyncio
    async def test_kpi_report_summary_and_list_agree(self, seeded):
        s = await _surfaces(seeded)
        expected_total = sum(_expected_book_values().values())
        summary, rows = s["costs"]["summary"], s["costs"]["rows"]
        asset_value = s["kpi"]["assetValue"]

        report_total = sum(_cents(r["Book Value"]) or 0 for r in s["report"]["rows"])
        list_total = sum(r["bookValueCents"] for r in rows if r["bookValueCents"] is not None)
        assert expected_total > 0
        assert asset_value["totalBookValueCents"] == expected_total
        assert summary["bookValueTotal"] == {"cents": expected_total, "hasData": True}
        assert report_total == expected_total
        assert list_total == expected_total
        assert asset_value["valuedCount"] == summary["coverage"]["valued"] == len(_expected_book_values())
        assert asset_value["inScopeAssetCount"] == summary["coverage"]["total"] == len(_active_tags())

    @pytest.mark.asyncio
    async def test_report_matches_list_row_for_row(self, seeded):
        s = await _surfaces(seeded)
        by_tag = _rows_by_tag(s["costs"])
        # The report population: a stored cost and date, not disposed or retired (Phase 78 A-78-14).
        population = [t for t, st, cost, date, _ in SPEC
                      if cost is not None and date is not None and st not in INACTIVE]
        report_tags = [r["Asset Tag"] for r in s["report"]["rows"]]
        assert sorted(report_tags) == sorted(population)
        assert report_tags == [r["assetTag"] for r in s["costs"]["rows"] if r["assetTag"] in set(population)]
        for row in s["report"]["rows"]:
            assert _cents(row["Book Value"]) == by_tag[row["Asset Tag"]]["bookValueCents"]
            assert row["Reason"] == (by_tag[row["Asset Tag"]]["reason"] or "—")
        for tag, expected in _expected_book_values().items():
            assert by_tag[tag]["bookValueCents"] == expected

    @pytest.mark.asyncio
    async def test_book_value_route_matches_list(self, seeded, monkeypatch):
        monkeypatch.setattr(itam_finance_endpoints, "get_database",
                            lambda: database.TenantIsolatedDatabase(seeded))
        user = make_token_data(tenant_id="tenant-p", role="admin", username="admin@example.com")
        s = await _surfaces(seeded)
        by_tag = _rows_by_tag(s["costs"])
        checked = 0
        for tag in _active_tags():
            if not isinstance(_cost_of(tag), int) and _cost_of(tag) is not None:
                continue  # a string cost is not a well-typed input for the per-asset route
            with _as_tenant("tenant-p"):
                result = await itam_finance_endpoints.get_asset_book_value(f"tenant-p:{tag}", user)
            assert result["bookValueCents"] == by_tag[tag]["bookValueCents"], tag
            checked += 1
        assert checked == len(_active_tags()) - 1

    @pytest.mark.asyncio
    async def test_salvage_above_cost_route_and_row_agree(self, seeded, monkeypatch):
        """WR-06: the per-asset route and the list row give one answer when salvage is above the price
        paid, and the same reason code for an asset whose model is missing."""
        monkeypatch.setattr(itam_finance_endpoints, "get_database",
                            lambda: database.TenantIsolatedDatabase(seeded))
        user = make_token_data(tenant_id="tenant-p", role="admin", username="admin@example.com")
        by_tag = _rows_by_tag((await _surfaces(seeded))["costs"])
        for tag, reason in (("N-SALVAGE", "salvage_exceeds_cost"), ("N-NOMODEL", "no_depreciation_policy_assigned")):
            with _as_tenant("tenant-p"):
                result = await itam_finance_endpoints.get_asset_book_value(f"tenant-p:{tag}", user)
            assert result["bookValueCents"] is None and by_tag[tag]["bookValueCents"] is None, tag
            assert result["reason"] == by_tag[tag]["reason"] == reason, tag

    @pytest.mark.asyncio
    async def test_lifecycle_rule_across_surfaces(self, seeded):
        s = await _surfaces(seeded)
        listed = {r["assetTag"] for r in s["costs"]["rows"]}
        assert not listed & {"X-DISPOSED", "X-RETIRED"}
        assert "X-DISPOSED" not in {r["Asset Tag"] for r in s["report"]["rows"]}
        assert "X-RETIRED" not in {r["Asset Tag"] for r in s["report"]["rows"]}
        base, wide = s["costs"]["summary"], s["with_inactive"]["summary"]
        assert wide["purchaseTotal"]["cents"] == base["purchaseTotal"]["cents"] + _cost_of("X-DISPOSED") + _cost_of("X-RETIRED")
        assert wide["bookValueTotal"] == base["bookValueTotal"]
        by_tag = _rows_by_tag(s["with_inactive"])
        for tag in ("X-DISPOSED", "X-RETIRED"):
            assert by_tag[tag]["bookValueCents"] is None
            assert by_tag[tag]["purchaseCostCents"] == _cost_of(tag)
        counts = {seg["status"]: seg["count"] for seg in s["kpi"]["assetValue"]["statusBreakdown"]}
        assert counts["disposed"] == 1 and counts["retired"] == 1
        assert s["kpi"]["assetValue"]["assetCount"] == len(SPEC)

    @pytest.mark.asyncio
    async def test_not_tracked_and_flags(self, seeded):
        s = await _surfaces(seeded)
        by_tag = _rows_by_tag(s["costs"])
        for tag, reason in NOT_TRACKED.items():
            assert by_tag[tag]["bookValueCents"] is None, tag
            assert by_tag[tag]["reason"] == reason, tag
        summary = s["costs"]["summary"]
        assert summary["coverage"]["reasons"]["unreadable_purchase_cost"] == 1
        assert summary["coverage"]["reasons"]["unreadable_purchase_date"] == 1
        # Nothing unreadable adds to either total.
        purchase = sum(c for t in _active_tags() if isinstance(c := _cost_of(t), int))
        assert summary["purchaseTotal"]["cents"] == purchase
        assert by_tag["N-ZERO"]["purchaseCostCents"] == 0 and by_tag["N-ZERO"]["bookValueCents"] == 0
        assert by_tag["N-ZERO"]["priced"] is True
        assert "futurePurchaseDate" in by_tag["N-FUTURE"]["flags"]
        assert by_tag["N-FUTURE"]["bookValueCents"] == _cost_of("N-FUTURE")
        for tag in ("N-AGENT", "N-HAND"):
            assert "possibleDuplicate" in by_tag[tag]["flags"], tag
        assert by_tag["N-AGENT"]["possibleDuplicateOf"] == ["tenant-p:N-HAND"]
        assert by_tag["N-HAND"]["possibleDuplicateOf"] == ["tenant-p:N-AGENT"]
        assert by_tag["N-HAND"]["bookValueCents"] == _expected_book_values()["N-HAND"]
        assert by_tag["N-AGENT"]["agent"]["agentId"] == "agent-p1"
        assert summary["coverage"]["possibleDuplicatePairs"] == 1
        assert summary["coverage"]["total"] == len(_active_tags())

    @pytest.mark.asyncio
    async def test_other_tenant_never_leaks(self, seeded):
        s = await _surfaces(seeded)
        text = repr(s)
        assert "tenant-q" not in text and "agent-q1" not in text
        assert 999000 not in {r["purchaseCostCents"] for r in s["with_inactive"]["rows"]}

    @pytest.mark.asyncio
    async def test_repeat_runs_identical(self, seeded):
        first = await _surfaces(seeded)
        second = await _surfaces(seeded)
        assert first == second
