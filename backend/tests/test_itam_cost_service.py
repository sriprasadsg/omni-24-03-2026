"""The shared per-asset cost computation (Phase 78, plan 78-09; COST-01, COST-02, COST-06, COST-07).

Value: protects=every ITAM cost figure (cost routes, KPI tile, Asset value report) because they all
come from itam_cost_service; it is pinned to the Phase 59 D-04 depreciation definition by a 13-row
golden table asserted on compute_book_value and on compute_asset_cost at the same clock, and its
reason, lifecycle, zero-price, future-date and null-not-zero rules are held from asset document to
tenant summary; fails_when=compute_asset_cost drifts from compute_book_value, an asset carries two
reasons or none while unvalued, a disposed or retired asset is valued or counted by default, a $0
price reads as unknown, or an empty or unpriced tenant reports 0 instead of no data;
no_claim=routes, authorization and the UI (the 78-01..78-07 suites own those).

Real throwaway MongoDB (mongo_db fixture, behind the production TenantIsolatedDatabase wrapper).
"""
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests._mongo_test_db import mongo_db  # noqa: F401 - fixture re-exported for pytest

import database
import itam_cost_service as svc
import tenant_context
from itam_finance_service import compute_book_value

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)
D = "2024-03-01"

# purchase date, cost, life, salvage, (y, m, d) of now, expected book value, expected years, future flag
GOLDEN = [
    pytest.param(D, 100000, 1, 10000, (2025, 2, 28), 100000, 0, False, id="life1-day-before-anniversary"),
    pytest.param(D, 100000, 1, 10000, (2025, 3, 1), 10000, 1, False, id="life1-on-anniversary"),
    pytest.param(D, 100000, 3, 150000, (2026, 6, 1), 150000, 2, False, id="salvage-above-cost-pinned"),
    pytest.param(D, 100000, 3, 100000, (2026, 6, 1), 100000, 2, False, id="salvage-equals-cost"),
    pytest.param(D, 0, 3, 0, (2026, 6, 1), 0, 2, False, id="cost-zero"),
    pytest.param("2024-02-29", 120000, 4, 0, (2025, 2, 28), 120000, 0, False, id="leap-day-before"),
    pytest.param("2024-02-29", 120000, 4, 0, (2025, 3, 1), 90000, 1, False, id="leap-day-after"),
    pytest.param("2023-06-15", 150000, 3, 15000, (2024, 6, 14), 150000, 0, False, id="anniversary-eve"),
    pytest.param("2023-06-15", 150000, 3, 15000, (2024, 6, 15), 105000, 1, False, id="anniversary-day"),
    pytest.param("2030-01-01", 100000, 3, 10000, (2026, 11, 16), 100000, 0, True, id="future-purchase-date"),
    pytest.param("2020-01-01", 100001, 3, 0, (2026, 11, 16), 2, 3, False, id="integer-division"),
    pytest.param("2015-01-01", 100000, 3, 10000, (2026, 11, 16), 10000, 3, False, id="past-end-of-life"),
    pytest.param("2024-03-01T00:00:00Z", 100000, 2, 0, (2026, 11, 16), 0, 2, False, id="z-suffix-date"),
]


def _asset(asset_id="A1", *, cost=None, date=None, status="deployed", model_id="m1", name=None, tag=None):
    doc = {"id": asset_id, "name": name or asset_id, "assetTag": tag or f"TAG-{asset_id}", "modelId": model_id}
    if status is not None:
        doc["lifecycleStatus"] = status
    if cost is not None:
        doc["purchaseCostCents"] = cost
    if date is not None:
        doc["purchaseDate"] = date
    return doc


def _model(life=3, salvage=10000, model_id="m1"):
    return {"id": model_id, "usefulLifeYears": life, "salvageValueCents": salvage}


@contextmanager
def ambient(tenant):
    token = tenant_context.set_tenant_id(tenant)
    try:
        yield
    finally:
        tenant_context.reset_tenant_id(token)


async def _tenant_costs(raw_db, tenant, assets, models=(), **kwargs):
    """Seed one tenant through the raw database, read through the production wrapper."""
    if assets:
        await raw_db.assets.insert_many([{**a, "tenantId": tenant} for a in assets])
    if models:
        await raw_db.asset_models.insert_many([{**m, "tenantId": tenant} for m in models])
    with ambient(tenant):
        return await svc.compute_tenant_costs(database.TenantIsolatedDatabase(raw_db), tenant, now=NOW, **kwargs)


@pytest.mark.parametrize("date,cost,life,salvage,day,book,years,future", GOLDEN)
def test_golden_table(date, cost, life, salvage, day, book, years, future):
    now = datetime(*day, 12, 0, tzinfo=timezone.utc)
    direct = compute_book_value(
        purchase_date=date, purchase_cost_cents=cost, useful_life_years=life, salvage_value_cents=salvage, now=now
    )
    assert (direct["bookValueCents"], direct["yearsElapsed"]) == (book, years)

    row = svc.compute_asset_cost(_asset(cost=cost, date=date), _model(life, salvage), now)
    assert (row["bookValueCents"], row["yearsElapsed"]) == (book, years)
    assert type(row["bookValueCents"]) is int
    assert row["reason"] is None and row["valued"] is True and row["priced"] is True
    assert (svc.FLAG_FUTURE_PURCHASE_DATE in row["flags"]) is future


async def test_reason_precedence_and_invariant(mongo_db):
    assets = [
        _asset("V1", cost=120000, date=D),
        _asset("V2", cost=50000, date=D, status=None),
        _asset("DISP", cost=90000, date=D, status="disposed"),
        _asset("RET", cost=80000, date=D, status="retired"),
        _asset("BADCOST", cost="100000", date=D),
        _asset("NOREC", cost=None, date=D),
        _asset("NODATE", cost=70000, date=None),
        _asset("NOPOL", cost=60000, date=D, model_id="gone"),
        _asset("BADDATE", cost=40000, date="not-a-date"),
    ]
    result = await _tenant_costs(mongo_db, "t1", assets, [_model()], include_inactive=True)
    by_id = {r["assetId"]: r for r in result["rows"]}
    assert by_id["DISP"]["reason"] == svc.REASON_DISPOSED
    assert by_id["RET"]["reason"] == svc.REASON_RETIRED
    assert by_id["BADCOST"]["reason"] == svc.REASON_UNREADABLE_COST
    assert by_id["NOREC"]["reason"] == svc.REASON_NO_PURCHASE_RECORD
    assert by_id["NODATE"]["reason"] == svc.REASON_NO_PURCHASE_RECORD
    assert by_id["NOPOL"]["reason"] == svc.REASON_NO_DEPRECIATION_POLICY
    assert by_id["BADDATE"]["reason"] == svc.REASON_UNREADABLE_DATE
    assert by_id["V1"]["reason"] is None and by_id["V2"]["reason"] is None

    for include in (False, True):
        with ambient("t1"):
            out = await svc.compute_tenant_costs(
                database.TenantIsolatedDatabase(mongo_db), "t1", include_inactive=include, now=NOW
            )
        cov = out["summary"]["coverage"]
        assert cov["total"] == len(out["rows"]) == (9 if include else 7)
        assert cov["valued"] + sum(cov["reasons"].values()) == cov["total"]
        for row in out["rows"]:
            assert (row["reason"] is None) == row["valued"]
            assert row["reason"] is None or row["reason"] in svc.REASON_CODES


async def test_lifecycle_rule(mongo_db):
    statuses = ["disposed", "retired", "archived", "broken", "deployable", "deployed", None]
    assets = [_asset(f"S{i}", cost=100000, date=D, status=s) for i, s in enumerate(statuses)]
    models = [_model()]

    row_of = {i: svc.compute_asset_cost(a, models[0], NOW) for i, a in enumerate(assets)}
    for i in (0, 1):
        row = row_of[i]
        assert row["reason"] == statuses[i] and row["bookValueCents"] is None
        assert row["purchaseCostCents"] == 100000 and row["priced"] is True
    for i in range(2, 7):
        assert row_of[i]["reason"] is None and row_of[i]["valued"] is True
    assert row_of[6]["lifecycleStatus"] == "deployable"

    default = await _tenant_costs(mongo_db, "t1", assets, models)
    assert {r["assetId"] for r in default["rows"]} == {"S2", "S3", "S4", "S5", "S6"}
    assert default["summary"]["coverage"]["excludedByLifecycle"] == 2
    assert default["summary"]["includeDisposed"] is False
    assert default["summary"]["purchaseTotal"]["cents"] == 500000

    with ambient("t1"):
        everything = await svc.compute_tenant_costs(
            database.TenantIsolatedDatabase(mongo_db), "t1", include_inactive=True, now=NOW
        )
    assert len(everything["rows"]) == 7
    assert everything["summary"]["coverage"]["excludedByLifecycle"] == 0
    assert everything["summary"]["purchaseTotal"]["cents"] == 700000


async def test_zero_price_is_priced(mongo_db):
    result = await _tenant_costs(mongo_db, "t1", [_asset("Z", cost=0, date=D, model_id=None)])
    assert result["summary"]["purchaseTotal"] == {"cents": 0, "hasData": True}
    assert result["summary"]["bookValueTotal"] == {"cents": None, "hasData": False}
    row = result["rows"][0]
    assert row["priced"] is True and row["purchaseCostCents"] == 0
    assert row["reason"] == svc.REASON_NO_DEPRECIATION_POLICY


async def test_future_date_flag(mongo_db):
    assets = [_asset("F", cost=100000, date="2030-01-01"), _asset("P", cost=100000, date=D)]
    result = await _tenant_costs(mongo_db, "t1", assets, [_model(3, 10000)])
    by_id = {r["assetId"]: r for r in result["rows"]}
    assert by_id["F"]["bookValueCents"] == 100000 and by_id["F"]["yearsElapsed"] == 0
    assert by_id["F"]["flags"] == [svc.FLAG_FUTURE_PURCHASE_DATE]
    assert by_id["P"]["flags"] == []
    assert result["summary"]["coverage"]["flags"][svc.FLAG_FUTURE_PURCHASE_DATE] == 1


def test_asset_level_policy_fields_ignored():
    asset = _asset("A", cost=100000, date=D, model_id=None)
    asset.update({"useful_life_years": 1, "salvage_value": 0.0, "usefulLifeYears": 1, "salvageValueCents": 0})
    row = svc.compute_asset_cost(asset, None, NOW)
    assert row["reason"] == svc.REASON_NO_DEPRECIATION_POLICY
    assert row["bookValueCents"] is None and row["priced"] is True
    # the model's own (missing or malformed) policy decides, never the asset's fields
    with_empty_model = svc.compute_asset_cost(asset, {"id": "m1"}, NOW)
    assert with_empty_model["reason"] == svc.REASON_NO_DEPRECIATION_POLICY


@pytest.mark.parametrize("model", [
    pytest.param(None, id="no-model"),
    pytest.param({"id": "m", "salvageValueCents": 0}, id="life-missing"),
    pytest.param({"id": "m", "usefulLifeYears": 0, "salvageValueCents": 0}, id="life-zero"),
    pytest.param({"id": "m", "usefulLifeYears": -2, "salvageValueCents": 0}, id="life-negative"),
    pytest.param({"id": "m", "usefulLifeYears": True, "salvageValueCents": 0}, id="life-bool"),
    pytest.param({"id": "m", "usefulLifeYears": 3}, id="salvage-missing"),
    pytest.param({"id": "m", "usefulLifeYears": 3, "salvageValueCents": -1}, id="salvage-negative"),
])
def test_unusable_model_policy_is_purchase_only(model):
    row = svc.compute_asset_cost(_asset(cost=100000, date=D), model, NOW)
    assert row["priced"] is True and row["purchaseCostCents"] == 100000
    assert row["bookValueCents"] is None
    assert row["reason"] == svc.REASON_NO_DEPRECIATION_POLICY


async def test_summary_has_data_convention(mongo_db):
    empty = await _tenant_costs(mongo_db, "empty", [])
    nothing = {"cents": None, "hasData": False}
    assert empty["summary"]["purchaseTotal"] == nothing and empty["summary"]["bookValueTotal"] == nothing

    unpriced = await _tenant_costs(
        mongo_db, "unpriced", [_asset("U1", cost=None, date=D), _asset("U2", cost="oops", date=D)], [_model()]
    )
    assert unpriced["summary"]["purchaseTotal"] == nothing
    assert unpriced["summary"]["bookValueTotal"] == nothing

    priced = await _tenant_costs(
        mongo_db, "priced", [_asset("P1", cost=100000, date=D, model_id=None), _asset("P2", cost=5000, date=D, model_id=None)]
    )
    assert priced["summary"]["purchaseTotal"] == {"cents": 105000, "hasData": True}
    assert priced["summary"]["bookValueTotal"] == nothing
    assert priced["summary"]["coverage"]["priced"] == 2 and priced["summary"]["coverage"]["valued"] == 0
