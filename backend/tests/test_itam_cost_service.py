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


# purchase date, cost, life, salvage, (y, m, d) of now: the finance function stays pinned (it floors at
# salvage, which is above the price paid); the cost row marks the asset instead of reporting that figure.
GOLDEN_SALVAGE_ABOVE_COST = [
    pytest.param(D, 100000, 3, 150000, (2026, 6, 1), 150000, id="salvage-above-cost"),
    pytest.param(D, 100000, 3, 100001, (2026, 6, 1), 100002, id="salvage-one-cent-above-cost"),
    pytest.param(D, 0, 3, 1, (2026, 6, 1), 2, id="cost-zero-salvage-one"),
]


@pytest.mark.parametrize("date,cost,life,salvage,day,finance_book", GOLDEN_SALVAGE_ABOVE_COST)
def test_salvage_above_cost_is_marked_not_valued(date, cost, life, salvage, day, finance_book):
    now = datetime(*day, 12, 0, tzinfo=timezone.utc)
    direct = compute_book_value(
        purchase_date=date, purchase_cost_cents=cost, useful_life_years=life, salvage_value_cents=salvage, now=now
    )
    # the shared function is unchanged and never clamps: its figure is above the price paid
    assert direct["bookValueCents"] == finance_book and finance_book > cost

    row = svc.compute_asset_cost(_asset(cost=cost, date=date), _model(life, salvage), now)
    assert row["bookValueCents"] is None and row["yearsElapsed"] is None and row["valued"] is False
    assert row["reason"] == svc.REASON_NO_DEPRECIATION_POLICY
    assert row["priced"] is True and row["purchaseCostCents"] == cost


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


# ---------------------------------------------------------------- guards (78-09 Task 2)

def _floats_in(value):
    if isinstance(value, float):
        return [value]
    if isinstance(value, dict):
        return [f for v in value.values() for f in _floats_in(v)]
    if isinstance(value, (list, tuple)):
        return [f for v in value for f in _floats_in(v)]
    return []


@pytest.mark.parametrize("cost", ["100000", 100000.5, 100000.0, -5, True, False, [1], {"c": 1}])
def test_malformed_cost_is_unreadable_never_a_float(cost):
    row = svc.compute_asset_cost(_asset(cost=cost, date=D), _model(), NOW)
    assert row["reason"] == svc.REASON_UNREADABLE_COST
    assert row["purchaseCostCents"] is None and row["priced"] is False and row["valued"] is False
    assert _floats_in(row) == []


@pytest.mark.parametrize("model", [
    {"id": "m", "usefulLifeYears": True, "salvageValueCents": 0},
    {"id": "m", "usefulLifeYears": 0, "salvageValueCents": 0},
    {"id": "m", "usefulLifeYears": 3.0, "salvageValueCents": 0},
    {"id": "m", "usefulLifeYears": 3, "salvageValueCents": 0.0},
    {"id": "m", "usefulLifeYears": "3", "salvageValueCents": 0},
])
def test_malformed_policy_is_no_policy(model):
    row = svc.compute_asset_cost(_asset(cost=100000, date=D), model, NOW)
    assert row["reason"] == svc.REASON_NO_DEPRECIATION_POLICY
    assert row["priced"] is True and row["bookValueCents"] is None
    assert _floats_in(row) == []


@pytest.mark.parametrize("date", [datetime(2024, 3, 1), datetime(2024, 3, 1, tzinfo=timezone.utc), "not-a-date",
                                  "", True, 20240301, b"2024-03-01"])
def test_malformed_date_is_unreadable_and_only_strings_are_echoed(date):
    asset = _asset(cost=100000, date=D)
    asset["purchaseDate"] = date
    row = svc.compute_asset_cost(asset, _model(), NOW)
    assert row["reason"] == svc.REASON_UNREADABLE_DATE
    # only a string is echoed back; any other type (a datetime object, a bool) is reported as null
    assert row["purchaseDate"] == (date if isinstance(date, str) else None)
    assert row["bookValueCents"] is None and row["priced"] is True
    assert _floats_in(row) == []


@pytest.mark.parametrize("status", [["deployed"], {"s": "disposed"}, 5, 1.5, True, ""])
def test_malformed_lifecycle_status_reads_as_default(status):
    asset = _asset(cost=100000, date=D)
    asset["lifecycleStatus"] = status
    row = svc.compute_asset_cost(asset, _model(), NOW)
    assert row["lifecycleStatus"] == "deployable"
    assert row["reason"] is None and row["valued"] is True


def test_malformed_inputs_never_raise():
    """The plan's combined case list in one place: none raises and no result value is a float."""
    cases = [
        (_asset(cost="100000", date=D), _model(), svc.REASON_UNREADABLE_COST),
        (_asset(cost=100000.5, date=D), _model(), svc.REASON_UNREADABLE_COST),
        (_asset(cost=-5, date=D), _model(), svc.REASON_UNREADABLE_COST),
        (_asset(cost=True, date=D), _model(), svc.REASON_UNREADABLE_COST),
        (_asset(cost=100000, date=D), _model(life=True), svc.REASON_NO_DEPRECIATION_POLICY),
        (_asset(cost=100000, date=D), _model(life=0), svc.REASON_NO_DEPRECIATION_POLICY),
        (_asset(cost=100000, date="not-a-date"), _model(), svc.REASON_UNREADABLE_DATE),
        ({**_asset(cost=100000), "purchaseDate": datetime(2024, 3, 1)}, _model(), svc.REASON_UNREADABLE_DATE),
    ]
    for asset, model, reason in cases:
        row = svc.compute_asset_cost(asset, model, NOW)
        assert row["reason"] == reason and row["bookValueCents"] is None
        assert _floats_in(row) == []
    assert row["purchaseDate"] is None  # the datetime object is not echoed


def test_empty_document_never_raises():
    row = svc.compute_asset_cost({}, None, NOW)
    assert row["reason"] == svc.REASON_NO_PURCHASE_RECORD and row["priced"] is False and row["valued"] is False


async def test_malformed_documents_do_not_fail_the_tenant_read(mongo_db):
    assets = [
        _asset("OK", cost=100000, date=D, name="ok"),
        {**_asset("L", cost=100000, date=D, name="listy"), "lifecycleStatus": ["deployed"]},
        {**_asset("N", cost=100000, date=D), "name": 123, "assetTag": 456},
        {**_asset("C", date=D, name="cost-float"), "purchaseCostCents": 99.5},
        {**_asset("T", cost=100000, name="date-obj"), "purchaseDate": datetime(2024, 3, 1)},
    ]
    result = await _tenant_costs(mongo_db, "t1", assets, [_model()])
    assert {r["assetId"] for r in result["rows"]} == {"OK", "L", "N", "C", "T"}
    cov = result["summary"]["coverage"]
    assert cov["valued"] + sum(cov["reasons"].values()) == cov["total"] == 5
    assert _floats_in(result["rows"]) == [] and _floats_in(result["summary"]) == []


class _Untouchable:
    """A database stand-in that fails the test when anything reads from it."""

    def __getattr__(self, name):
        raise AssertionError(f"the refused call reached the database ({name})")


@pytest.mark.parametrize("bad", ["", None, "platform-admin"], ids=["empty", "none", "platform-admin"])
@pytest.mark.parametrize("call", [
    lambda db, t: svc.compute_tenant_costs(db, t),
    lambda db, t: svc.load_tenant_assets(db, t),
    lambda db, t: svc.load_models_by_id(db, t, [{"modelId": "m1"}]),
    lambda db, t: svc.load_agents_by_asset(db, t, ["A1"]),
], ids=["compute_tenant_costs", "load_tenant_assets", "load_models_by_id", "load_agents_by_asset"])
async def test_require_tenant_refuses_platform_admin_and_empty(call, bad):
    with pytest.raises(ValueError):
        await call(_Untouchable(), bad)


async def test_explicit_tenant_filter_under_platform_admin_ambient(mongo_db):
    await mongo_db.asset_models.insert_many([
        {"tenantId": "tenant-a", "id": "m1", "usefulLifeYears": 3, "salvageValueCents": 0},
        {"tenantId": "tenant-b", "id": "m1", "usefulLifeYears": 1, "salvageValueCents": 0},
    ])
    await mongo_db.assets.insert_many([
        {**_asset("A1", cost=100000, date=D), "tenantId": "tenant-a"},
        {**_asset("A2", cost=50000, date=D), "tenantId": "tenant-a"},
        {**_asset("B1", cost=777000, date=D), "tenantId": "tenant-b"},
    ])
    await mongo_db.agents.insert_many([
        {"tenantId": "tenant-a", "id": "ga", "assetId": "A1", "hostname": "a-host", "status": "Online"},
        {"tenantId": "tenant-b", "id": "gb", "assetId": "A1", "hostname": "b-host", "status": "Online"},
    ])
    wrapped = database.TenantIsolatedDatabase(mongo_db)
    with ambient("platform-admin"):
        # the premise: under this ambient the wrapper adds no tenant filter of its own
        assert len(await wrapped.assets.find({}).to_list(length=None)) == 3
        result = await svc.compute_tenant_costs(wrapped, "tenant-a", with_agents=True, now=NOW)
    assert {r["assetId"] for r in result["rows"]} == {"A1", "A2"}
    assert result["summary"]["tenantId"] == "tenant-a"
    assert result["summary"]["coverage"]["total"] == 2
    assert result["summary"]["purchaseTotal"]["cents"] == 150000
    by_id = {r["assetId"]: r for r in result["rows"]}
    assert by_id["A1"]["agent"]["agentId"] == "ga"  # tenant-b's agent naming A1 is not joined
    # tenant-a's own policy (3 years), not tenant-b's model of the same id (1 year)
    assert by_id["A1"]["yearsElapsed"] == 2 and by_id["A1"]["bookValueCents"] == 100000 - 2 * (100000 // 3)


def test_sort_order():
    def row(asset_id, book, name, tag):
        return {"assetId": asset_id, "bookValueCents": book, "name": name, "assetTag": tag}

    expected = [
        row("v1", 90000, "zeta", "T9"),
        row("v2", 50000, "alpha", "T5"),
        row("v3", 50000, "beta", "T1"),
        row("v4", 50000, "beta", "T2"),
        row("v5", 50000, "beta", "T2"),  # same name and tag: asset id decides
        row("v6", 0, "alpha", "T1"),     # a real 0 outranks every not-tracked row
        row("n1", None, "alpha", "T1"),
        row("n2", None, "alpha", "T2"),
        row("n3", None, "beta", "T0"),
    ]
    import random
    for seed in range(5):
        shuffled = list(expected)
        random.Random(seed).shuffle(shuffled)
        assert [r["assetId"] for r in svc.sort_cost_rows(shuffled)] == [r["assetId"] for r in expected]


def test_sort_tolerates_non_string_names_tags_and_ids():
    rows = [
        {"assetId": "b", "bookValueCents": 5, "name": "abc", "assetTag": None},
        {"assetId": "a", "bookValueCents": 5, "name": 123, "assetTag": 456},
        {"assetId": 7, "bookValueCents": None, "name": None, "assetTag": ["x"]},
    ]
    assert [r["assetId"] for r in svc.sort_cost_rows(rows)] == ["a", "b", 7]


async def test_one_utc_now_per_computation(mongo_db, monkeypatch):
    calls = []

    def counting_clock():
        calls.append(1)
        return NOW

    monkeypatch.setattr(svc, "utc_now", counting_clock)
    await mongo_db.assets.insert_many([
        {**_asset(f"A{i}", cost=100000, date=D), "tenantId": "t1"} for i in range(4)
    ])
    await mongo_db.asset_models.insert_one({**_model(), "tenantId": "t1"})
    wrapped = database.TenantIsolatedDatabase(mongo_db)
    with ambient("t1"):
        result = await svc.compute_tenant_costs(wrapped, "t1", with_agents=True)
        assert len(calls) == 1
        assert result["summary"]["computedAt"] == NOW.isoformat(timespec="milliseconds")
        await svc.compute_asset_cost_detail(wrapped, "t1", "A0")
    assert len(calls) == 2  # one more, from the one detail computation


def test_cost_modules_have_no_forbidden_constructs():
    from pathlib import Path

    backend = Path(__file__).resolve().parents[1]
    forbidden = ["$lookup", "@cached", "cache_service", "finance_filtered", "* 100", "/ 100", "float(", "db._db"]
    for name in ("itam_cost_service.py", "itam_tenant_scope.py", "itam_cost_endpoints.py"):
        source = (backend / name).read_text(encoding="utf-8")
        assert "def " in source, f"{name} was not read"
        found = [token for token in forbidden if token in source]
        assert found == [], f"{name} contains {found}"
    service_source = (backend / "itam_cost_service.py").read_text(encoding="utf-8")
    assert "from fastapi" not in service_source and "import fastapi" not in service_source
