"""License cost and its allocation (Phase 79, COST-04/COST-05: itam_license_cost, the License model and the
license routes). protects/fails_when/no_claim per test; the route tests use real MongoDB.
"""
import os
import random
import sys
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import database
import itam_asset_endpoints
import itam_license_cost as lc
import itam_license_endpoints
from api_key_auth import get_current_user_or_api_key
from authentication_service import get_current_user
from itam_models import LicenseCreate
from tenant_context import reset_tenant_id, set_tenant_id
from tests._mongo_test_db import mongo_db  # noqa: F401  (fixture)
from tests.conftest import make_test_app, make_token_data


def _lic(lid, cost, period, seats, name=None):
    return {"id": lid, "name": name or lid, "seatCount": seats, "costCents": cost, "costPeriod": period}


def _seat(lid, n, kind, target, day=1):
    return {"id": f"{lid}-{n:05d}", "licenseId": lid, "targetType": kind, "targetId": target,
            "assignedAt": f"2026-11-{day:02d}T00:00:00.000+00:00"}


def _balanced(out):
    for b in lc.BUCKETS:
        bucket = out["summary"][b]
        if bucket["hasData"]:
            assert bucket["allocatedCents"] + bucket["unattributedCents"] + bucket["idleCents"] == bucket["spendCents"]
            assert sum((e[b] or 0) for e in out["byAsset"].values()) == bucket["allocatedCents"]


def test_split_seats_sums_exactly_and_differs_by_at_most_a_cent():
    """protects=a license's seats add up to its amount in whole cents; fails_when=cents appear or vanish in
    rounding; no_claim=-"""
    for total, seats in [(100, 3), (0, 5), (7, 7), (999_999_999, 1_501), (1, 1000), (35988, 30)]:
        parts = lc.split_seats(total, seats)
        assert sum(parts) == total and len(parts) == seats and max(parts) - min(parts) <= 1
    assert lc.split_seats(500, 0) == []


@pytest.mark.parametrize("seed", range(40))
def test_allocated_plus_unattributed_plus_idle_is_spend_for_any_seat_configuration(seed):
    """protects=COST-05's invariant for random licenses (up to 2,500 seats, all three bases, assignments to
    assets, users, deleted assets, and more assignments than seats); fails_when=any cent is lost or double
    counted; no_claim=-"""
    rnd = random.Random(seed)
    assets = {f"asset-{i}" for i in range(rnd.randint(0, 40))}
    licenses, seats = [], []
    for n in range(rnd.randint(1, 6)):
        count = rnd.choice([0, 1, 3, 7, 1000, 1001, 2500])
        lid = f"lic-{n}"
        licenses.append(_lic(lid, rnd.randint(0, 50_000_000), rnd.choice(lc.PERIODS), count))
        for k in range(min(count + rnd.randint(0, 3), rnd.randint(0, count + 3))):
            kind = rnd.choice(["asset", "user", "asset"])
            target = rnd.choice(sorted(assets) + ["asset-gone"]) if kind == "asset" and assets else f"user-{k}"
            seats.append(_seat(lid, k, kind if kind == "user" or assets else "user", target, rnd.randint(1, 28)))
    in_scope = {a for a in assets if rnd.random() < 0.7}
    out = lc.allocate(licenses, seats, assets, in_scope)
    _balanced(out)
    for b in lc.BUCKETS:
        bucket = out["summary"][b]
        if bucket["hasData"]:
            shown = sum((e[b] or 0) for a, e in out["byAsset"].items() if a in in_scope)
            assert shown + bucket["allocatedToExcludedCents"] == bucket["allocatedCents"]


def test_bases_are_kept_apart_and_monthly_is_per_year():
    """protects=monthly cost reads as 12x per year beside annual, one-time apart; fails_when=one-time and
    yearly spend are added into one number; no_claim=currency"""
    out = lc.allocate([_lic("m", 1000, "monthly", 2), _lic("y", 5000, "annual", 1), _lic("o", 70000, "one_time", 1)],
                      [_seat("m", 1, "asset", "a1"), _seat("o", 1, "asset", "a1")], {"a1"}, {"a1"})
    s = out["summary"]
    assert (s["recurringAnnual"]["spendCents"], s["recurringAnnual"]["allocatedCents"], s["recurringAnnual"]["idleCents"]) == (17000, 6000, 11000)
    assert (s["oneTime"]["spendCents"], s["oneTime"]["allocatedCents"]) == (70000, 70000)
    row = lc.row_allocation(out["byAsset"], "a1")
    assert (row["recurringAnnualCents"], row["oneTimeCents"], row["pricedSeats"]) == (6000, 70000, 2)


def test_seats_go_in_assignment_order_and_overshoot_takes_nothing():
    """protects=the first-assigned seats take the remainder cents, assignments past seatCount (the seat race's
    brief overshoot) take none, a seat on a user or on a deleted asset is unattributed; fails_when=a seat
    is paid twice or a user seat is pinned to an endpoint; no_claim=-"""
    lic = _lic("l", 100, "annual", 3)
    seats = [_seat("l", 3, "asset", "a2", day=3), _seat("l", 1, "asset", "a1", day=1), _seat("l", 2, "user", "u", day=2),
             _seat("l", 4, "asset", "a3", day=4)]
    one = lc.allocate_license(lic, seats, {"a1", "a2", "a3"})
    assert one["allocated"] == {"a1": 34, "a2": 33} and one["unattributedCents"] == 33 and one["idleCents"] == 0
    assert one["seats"]["over"] == 1 and "a3" not in one["allocated"]
    gone = lc.allocate_license(_lic("l", 90, "annual", 3), [_seat("l", 1, "asset", "deleted")], set())
    assert gone["unattributedCents"] == 30 and gone["seats"]["orphaned"] == 1 and gone["idleCents"] == 60
    nobody = lc.allocate_license(_lic("l", 500, "one_time", 0), [], set())
    assert nobody["idleCents"] == 500 and nobody["seats"]["idle"] == 0


def test_a_license_without_cost_is_not_tracked_rather_than_zero():
    """protects=no cost means "not tracked" in coverage and on the row, while seats on priced licenses still
    count; fails_when=a missing cost shows as $0; no_claim=-"""
    out = lc.allocate([{"id": "free", "name": "Free", "seatCount": 5}, _lic("p", 0, "annual", 1)],
                      [_seat("free", 1, "asset", "a1"), _seat("p", 1, "asset", "a2")], {"a1", "a2"}, {"a1", "a2"})
    assert out["summary"]["coverage"] == {"total": 2, "priced": 1, "notTracked": 1}
    assert out["summary"]["oneTime"] == {**out["summary"]["oneTime"], "spendCents": None, "hasData": False}
    assert lc.row_allocation(out["byAsset"], "a1") == {"recurringAnnualCents": None, "oneTimeCents": None,
                                                       "pricedSeats": 0, "untrackedSeats": 1, "lines": []}
    assert lc.row_allocation(out["byAsset"], "a2")["recurringAnnualCents"] == 0  # priced at 0: a real zero
    assert lc.row_allocation(out["byAsset"], "a3")["pricedSeats"] == 0


@pytest.mark.parametrize("body,ok", [
    ({"costCents": 129900, "costPeriod": "annual"}, True),
    ({}, True),
    ({"costCents": 129900}, False),
    ({"costPeriod": "monthly"}, False),
    ({"costCents": 12.5, "costPeriod": "annual"}, False),
    ({"costCents": "1299", "costPeriod": "annual"}, False),
    ({"costCents": -1, "costPeriod": "annual"}, False),
    ({"costCents": 10**13 + 1, "costPeriod": "annual"}, False),
    ({"costCents": 100, "costPeriod": "weekly"}, False),
])
def test_the_license_model_takes_a_cost_only_with_its_basis(body, ok):
    """protects=COST-04: whole cents (no floats, strings or negatives) and a basis, both or neither;
    fails_when=a cost without a basis is stored and later summed wrongly; no_claim=-"""
    if ok:
        LicenseCreate(name="Office", seatCount=5, **body)
    else:
        with pytest.raises(ValidationError):
            LicenseCreate(name="Office", seatCount=5, **body)


@pytest_asyncio.fixture
async def client(mongo_db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(itam_license_endpoints, "get_database", lambda: database.TenantIsolatedDatabase(mongo_db))
    monkeypatch.setattr(itam_license_endpoints, "log_itam_action", AsyncMock())
    monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=True))
    app, _ = make_test_app(itam_license_endpoints.router)
    user = make_token_data(tenant_id="tenant-a", role="admin")
    app.dependency_overrides[get_current_user_or_api_key] = lambda: user
    app.dependency_overrides[get_current_user] = lambda: user
    token = set_tenant_id("tenant-a")
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
            yield ac, mongo_db
    finally:
        reset_tenant_id(token)


@pytest.mark.asyncio
async def test_routes_store_change_and_remove_a_cost_and_old_licenses_still_save(client):
    """protects=a cost is created with its basis, changed, refused without one, removed with costCents null,
    and a license without cost saves exactly as before; fails_when=PATCH drops the null (no way to remove a
    cost) or leaves a basis behind; no_claim=the UI"""
    ac, db = client
    plain = await ac.post("/api/itam/licenses", json={"name": "Old", "seatCount": 2})
    assert plain.status_code == 201 and "costCents" not in plain.json()
    made = await ac.post("/api/itam/licenses", json={"name": "Office", "seatCount": 5, "costCents": 129900, "costPeriod": "annual"})
    assert made.status_code == 201, made.text
    lid = made.json()["id"]
    assert (await ac.patch(f"/api/itam/licenses/{lid}", json={"costPeriod": "monthly"})).json()["costPeriod"] == "monthly"
    bad = await ac.patch(f"/api/itam/licenses/{plain.json()['id']}", json={"costCents": 500})
    assert bad.status_code == 422 and "go together" in bad.text
    gone = await ac.patch(f"/api/itam/licenses/{lid}", json={"costCents": None})
    assert gone.status_code == 200 and "costCents" not in gone.json() and "costPeriod" not in gone.json()
    stored = await db.licenses.find_one({"id": lid})
    assert "costCents" not in stored and "costPeriod" not in stored and stored["tenantId"] == "tenant-a"
    assert (await ac.patch(f"/api/itam/licenses/{plain.json()['id']}", json={"name": "Older"})).status_code == 200


@pytest.mark.asyncio
async def test_the_costs_export_holds_the_costs_tab_rows(mongo_db, monkeypatch):  # noqa: F811
    """protects=COST-08: the endpoint_costs report (the Costs tab's export) has the same rows, order and figures
    as GET /api/itam/costs/assets, including not-tracked and no-seat cells; fails_when=the download differs from
    the screen; no_claim=the PDF and XLSX renderers' layout"""
    import itam_cost_service
    import itam_reporting_prebuilt
    from datetime import datetime, timezone
    monkeypatch.setattr(itam_cost_service, "utc_now", lambda: datetime(2026, 11, 18, tzinfo=timezone.utc))
    t = "tenant-r"
    await mongo_db.asset_models.insert_one({"tenantId": t, "id": "m", "usefulLifeYears": 4, "salvageValueCents": 0})
    await mongo_db.assets.insert_many([
        {"tenantId": t, "id": "a1", "name": "Laptop", "assetTag": "T1", "modelId": "m", "purchaseCostCents": 150000,
         "purchaseDate": "2025-11-18T00:00:00+00:00", "lifecycleStatus": "deployed"},
        {"tenantId": t, "id": "a2", "name": "Desk PC", "assetTag": "T2", "lifecycleStatus": "deployed"},
        {"tenantId": t, "id": "a3", "name": "Old", "assetTag": "T3", "lifecycleStatus": "disposed"}])
    await mongo_db.agents.insert_one({"tenantId": t, "id": "ag1", "assetId": "a1", "hostname": "LAPTOP-1", "lastSeen": "x"})
    await mongo_db.licenses.insert_many([{"tenantId": t, **_lic("l1", 12000, "monthly", 4)},
                                         {"tenantId": t, "id": "l2", "name": "Free", "seatCount": 9}])
    await mongo_db.license_assignments.insert_many([{"tenantId": t, **_seat("l1", 1, "asset", "a1")},
                                                    {"tenantId": t, **_seat("l1", 2, "asset", "a3")},
                                                    {"tenantId": t, **_seat("l2", 1, "asset", "a2")}])
    tab = await itam_cost_service.compute_tenant_costs(mongo_db, t, with_agents=True, with_licenses=True)
    report = await itam_reporting_prebuilt.run_prebuilt_report(mongo_db, "endpoint_costs", t)
    assert [r["Asset Tag"] for r in report["rows"]] == [r["assetTag"] for r in tab["rows"]] == ["T1", "T2"]
    laptop, desk = report["rows"]
    assert (laptop["Endpoint"], laptop["Purchase Cost"], laptop["License Cost per Year"], laptop["One-Time License Cost"]) == \
        ("LAPTOP-1", "$1,500.00", "$360.00", "—")
    assert laptop["Book Value"] == f"${tab['rows'][0]['bookValueCents'] / 100:,.2f}"
    assert (desk["Purchase Cost"], desk["Book Value"], desk["License Cost per Year"]) == ("Not tracked", "Not tracked", "Not tracked")
    lic = tab["summary"]["licenses"]["recurringAnnual"]
    assert (lic["spendCents"], lic["allocatedCents"], lic["allocatedToExcludedCents"], lic["idleCents"]) == (144000, 72000, 36000, 72000)
