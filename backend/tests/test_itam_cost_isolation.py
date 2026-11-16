"""Two-tenant isolation proof for the ITAM cost, KPI and Asset value report routes (Phase 78, plan 78-07,
COST-07). Real MongoDB (skipped without one, and a skip is a failed gate), the real TenantMiddleware, real
signed session tokens, and the real route guards and tenant resolver.

Value: protects=a Platform Owner who switches organization with X-Tenant-ID reads only that organization's
figures (never a blend, never the organization of the token), and a tenant user never sees another
tenant's figures, asset ids or tags, even when the two tenants hold assets with identical names, tags,
serial numbers and model ids; fails_when=any response carries the other tenant's asset id, cost or book
value, an Owner without a chosen tenant gets a figure instead of 400, Support or Billing gets a figure, or
concurrent requests for two tenants mix their results; no_claim=the browser, the tenant switcher UI, and
unit-level formulas (the 78-01..78-05 suites own those).

The route suites of the earlier plans replace authentication, so only this module runs the step in the
token check that resets the per-request tenant to the token's own tenant after the middleware applied the
Owner's choice. That reset is what the shared resolver exists to defeat (RESEARCH Pitfall 1), so nothing
here replaces authentication, the permission check, the resolver or the per-request tenant.
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests._mongo_test_db import mongo_db  # noqa: F401 - fixture re-exported for pytest

import database
import itam_cost_endpoints
import itam_cost_service
import itam_kpi_endpoints
import itam_reporting_endpoints
import itam_reporting_service
import rbac_utils
from authentication_service import create_access_token
from itam_finance_service import compute_book_value
from tenant_middleware import TenantMiddleware

FIXED_NOW = datetime(2026, 11, 16, 12, 0, 0, tzinfo=timezone.utc)
PURCHASE = (FIXED_NOW - timedelta(days=400)).isoformat()

SUMMARY = "/api/itam/costs/summary"
ASSETS = "/api/itam/costs/assets"
KPIS = "/api/itam/kpis"
REPORT_RUN = "/api/itam/reports/prebuilt/asset_value/run"
REPORT_EXPORT = "/api/itam/reports/prebuilt/asset_value/export"

TENANTS = ("tenant-a", "tenant-b")
# Same names, tags, serial numbers and model id in both tenants; only ids, costs, policy and seats differ.
SHAPES = (
    {"n": 1, "name": "Laptop One", "tag": "TAG-100", "serial": "SER-0001"},
    {"n": 2, "name": "Server Two", "tag": "TAG-200", "serial": "SER-0002"},
)
DATA = {
    "tenant-a": {"key": "a", "costs": (120000, 54321), "life": 3, "salvage": 10000, "seats": 7},
    "tenant-b": {"key": "b", "costs": (345600, 87650), "life": 4, "salvage": 0, "seats": 30},
}


def _ids(tenant):
    return [f"{DATA[tenant]['key']}-asset-{n}" for n in (1, 2, 3)]


def _books(tenant):
    d = DATA[tenant]
    return [compute_book_value(PURCHASE, c, d["life"], d["salvage"], FIXED_NOW)["bookValueCents"] for c in d["costs"]]


def _dollars(cents):
    return f"${cents / 100:,.2f}"


def _other(tenant):
    return TENANTS[1] if tenant == TENANTS[0] else TENANTS[0]


def _foreign(tenant):
    """What only the other tenant owns: id fragments, its agent id, its money in cents and in dollars."""
    o = _other(tenant)
    d = DATA[o]
    return {
        "strings": [f"{d['key']}-asset-", f"agent-{d['key']}-", o]
        + [_dollars(c) for c in (*d["costs"], sum(d["costs"]), *_books(o), sum(_books(o)))],
        "numbers": {*d["costs"], sum(d["costs"]), *_books(o), sum(_books(o))},
    }


def _leaves(node):
    if isinstance(node, dict):
        for value in node.values():
            yield from _leaves(value)
    elif isinstance(node, list):
        for value in node:
            yield from _leaves(value)
    else:
        yield node


def token(role, tenant, sub=None):
    return create_access_token({"sub": sub or f"{role}@{tenant}", "role": role, "tenant_id": tenant, "mfa_verified": True})


@pytest.fixture(autouse=True)
def _fixed_clock(monkeypatch):
    monkeypatch.setattr(itam_cost_service, "utc_now", lambda: FIXED_NOW)


@pytest.fixture(autouse=True)
def _reports_dir_untouched():
    """Export files this module creates are removed (also by the helper that reads them)."""
    before = set(os.listdir(itam_reporting_service._REPORTS_DIR)) if os.path.isdir(itam_reporting_service._REPORTS_DIR) else set()
    yield
    for name in set(os.listdir(itam_reporting_service._REPORTS_DIR)) - before:
        os.remove(os.path.join(itam_reporting_service._REPORTS_DIR, name))


@pytest_asyncio.fixture
async def two_tenants(mongo_db):
    for tenant in TENANTS:
        d = DATA[tenant]
        await mongo_db.asset_models.insert_one(
            {"tenantId": tenant, "id": "model-std", "usefulLifeYears": d["life"], "salvageValueCents": d["salvage"]})
        ids = _ids(tenant)
        docs = [
            {"tenantId": tenant, "id": ids[i], "name": s["name"], "assetTag": s["tag"], "serialNumber": s["serial"],
             "lifecycleStatus": "deployed", "modelId": "model-std", "purchaseCostCents": d["costs"][i],
             "purchaseDate": PURCHASE}
            for i, s in enumerate(SHAPES)
        ]
        # The agent-discovered twin of the first laptop: same serial, so it pairs with it inside this tenant only.
        docs.append({"tenantId": tenant, "id": ids[2], "name": "Agent Box", "assetTag": "TAG-300",
                     "hardwareKey": "serial:SER-0001", "lifecycleStatus": "deployed", "modelId": "model-std"})
        await mongo_db.assets.insert_many(docs)
        await mongo_db.licenses.insert_one(
            {"tenantId": tenant, "id": f"lic-{d['key']}", "name": "Office suite", "seatCount": d["seats"]})
        await mongo_db.agents.insert_one(
            {"tenantId": tenant, "id": f"agent-{d['key']}-1", "assetId": ids[2], "hostname": "agent-box-host",
             "status": "Online", "lastSeen": "2026-11-16T10:00:00Z"})
    return mongo_db


@pytest.fixture
def app(monkeypatch, two_tenants):
    # The role store the permission check reads is the same throwaway database, so a role outside the
    # built-in table is refused on its merits and not because no database is connected.
    for module in (itam_cost_endpoints, itam_kpi_endpoints, itam_reporting_endpoints, itam_reporting_service, rbac_utils):
        monkeypatch.setattr(module, "get_database", lambda: database.TenantIsolatedDatabase(two_tenants))
    application = FastAPI()
    application.add_middleware(TenantMiddleware)
    for module in (itam_cost_endpoints, itam_kpi_endpoints, itam_reporting_endpoints):
        application.include_router(module.router)
    return application


@pytest_asyncio.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def get_summary(client, bearer, header=None):
    headers = {"Authorization": f"Bearer {bearer}", **({"X-Tenant-ID": header} if header is not None else {})}
    return await client.get(SUMMARY, headers=headers)


def assert_own_summary(response, tenant):
    assert response.status_code == 200, response.text
    body = response.json()
    d = DATA[tenant]
    assert body["tenantId"] == tenant
    assert body["purchaseTotal"] == {"cents": sum(d["costs"]), "hasData": True}
    assert body["bookValueTotal"] == {"cents": sum(_books(tenant)), "hasData": True}
    assert body["coverage"]["total"] == 3
    assert not (set(_leaves(body)) & _foreign(tenant)["numbers"])


class TestOwnerSwitch:
    @pytest.mark.asyncio
    async def test_owner_header_reads_only_that_tenant(self, client):
        owner = token("Super Admin", "platform-admin")
        assert sum(DATA["tenant-b"]["costs"]) != sum(DATA["tenant-a"]["costs"])
        assert_own_summary(await get_summary(client, owner, "tenant-b"), "tenant-b")
        assert_own_summary(await get_summary(client, owner, "tenant-a"), "tenant-a")

    @pytest.mark.asyncio
    async def test_tenant_admins_read_their_own_summary(self, client):
        for tenant in TENANTS:
            assert_own_summary(await get_summary(client, token("admin", tenant)), tenant)

    @pytest.mark.asyncio
    async def test_owner_without_header_is_400(self, client):
        response = await get_summary(client, token("Super Admin", "platform-admin"))
        assert response.status_code == 400
        assert response.json()["detail"].startswith("Select a tenant")


# ── The full route matrix ────────────────────────────────────────────────────────────────────────────

ROUTES = ("summary", "assets", "asset_detail", "kpis", "report_run", "report_export")
COST_AND_KPI = ("summary", "assets", "asset_detail", "kpis")
REPORT_ROUTES = ("report_run", "report_export")


class Result:
    def __init__(self, response, csv_text=""):
        self.status = response.status_code
        self.text = response.text + csv_text
        try:
            self.json = response.json()
        except ValueError:
            self.json = None


async def call(client, route, bearer, *, header=None, id_of="tenant-a"):
    """One request to a route. The detail route asks for the first asset of ``id_of``; the export is read
    from the file it wrote and that file is removed right away."""
    headers = {"Authorization": f"Bearer {bearer}", **({"X-Tenant-ID": header} if header is not None else {})}
    if route == "summary":
        return Result(await client.get(SUMMARY, headers=headers))
    if route == "assets":
        return Result(await client.get(ASSETS, headers=headers))
    if route == "asset_detail":
        return Result(await client.get(f"{ASSETS}/{_ids(id_of)[0]}", headers=headers))
    if route == "kpis":
        return Result(await client.get(KPIS, headers=headers))
    if route == "report_run":
        return Result(await client.post(REPORT_RUN, headers=headers))
    response = await client.post(REPORT_EXPORT, params={"format": "csv"}, headers=headers)
    csv_text = ""
    if response.status_code == 200:
        path = os.path.join(itam_reporting_service._REPORTS_DIR, response.json()["filename"])
        try:
            with open(path, encoding="utf-8") as handle:
                csv_text = handle.read()
        finally:
            os.remove(path)
    return Result(response, csv_text)


def assert_own(route, result, tenant):
    """The route answered 200 with exactly this tenant's seeded figures."""
    assert result.status == 200, result.text
    d = DATA[tenant]
    body = result.json
    if route == "summary":
        assert body["tenantId"] == tenant
        assert body["purchaseTotal"]["cents"] == sum(d["costs"])
        assert body["bookValueTotal"]["cents"] == sum(_books(tenant))
        assert body["coverage"]["total"] == 3
    elif route == "assets":
        assert body["tenantId"] == tenant and body["total"] == 3
        assert {row["assetId"] for row in body["items"]} == set(_ids(tenant))
    elif route == "asset_detail":
        assert body["assetId"] == _ids(tenant)[0]
        assert body["purchaseCostCents"] == d["costs"][0] and body["bookValueCents"] == _books(tenant)[0]
    elif route == "kpis":
        assert body["licenseUtilization"]["seatsTotal"] == d["seats"]
        assert body["assetValue"]["totalBookValueCents"] == sum(_books(tenant))
    elif route == "report_run":
        assert body["rowCount"] == 2
        assert {row["Purchase Cost"] for row in body["rows"]} == {_dollars(c) for c in d["costs"]}
        assert {row["Book Value"] for row in body["rows"]} == {_dollars(b) for b in _books(tenant)}
    else:
        assert body["rowCount"] == 2
        for cents in (*d["costs"], *_books(tenant)):
            assert _dollars(cents) in result.text
        assert "TAG-100" in result.text and "TAG-200" in result.text


def assert_no_foreign(result, tenant):
    """Nothing only the other tenant owns appears anywhere in the response (or exported file)."""
    foreign = _foreign(tenant)
    for needle in foreign["strings"]:
        assert needle not in result.text, f"{needle!r} leaked into a {tenant} response"
    if result.json is not None:
        assert not (set(_leaves(result.json)) & foreign["numbers"])


def assert_no_figure(result):
    """A refused response carries no id, cost or book value of either tenant."""
    for tenant in TENANTS:
        for needle in _foreign(tenant)["strings"]:
            assert needle not in result.text
        if result.json is not None:
            assert not (set(_leaves(result.json)) & _foreign(tenant)["numbers"])


class TestTenantIsolation:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("route", ROUTES)
    @pytest.mark.parametrize("tenant", TENANTS)
    async def test_tenant_a_never_sees_tenant_b(self, client, route, tenant):
        result = await call(client, route, token("admin", tenant), id_of=tenant)
        assert_own(route, result, tenant)
        assert_no_foreign(result, tenant)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tenant", TENANTS)
    async def test_foreign_detail_id_is_404(self, client, tenant):
        foreign_id = _ids(_other(tenant))[0]
        bearer = token("admin", tenant)
        foreign = await client.get(f"{ASSETS}/{foreign_id}", headers={"Authorization": f"Bearer {bearer}"})
        unknown = await client.get(f"{ASSETS}/no-such-asset", headers={"Authorization": f"Bearer {bearer}"})
        assert foreign.status_code == 404 and unknown.status_code == 404
        assert foreign.content == unknown.content

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tenant", TENANTS)
    async def test_tenant_admin_header_spoof_is_ignored(self, client, tenant):
        for route in ROUTES:
            result = await call(client, route, token("admin", tenant), header=_other(tenant), id_of=tenant)
            assert_own(route, result, tenant)
            assert_no_foreign(result, tenant)

    @pytest.mark.asyncio
    async def test_viewer_without_view_itam_is_403(self, client):
        for route in COST_AND_KPI:
            result = await call(client, route, token("viewer", "tenant-a"))
            assert result.status == 403, route
            assert_no_figure(result)


class TestPlatformRoles:
    @pytest.mark.asyncio
    async def test_owner_without_tenant_is_400_everywhere(self, client):
        for route in ROUTES:
            result = await call(client, route, token("Super Admin", "platform-admin"))
            assert result.status == 400, route
            assert result.json["detail"].startswith("Select a tenant"), route
            assert_no_figure(result)

    @pytest.mark.asyncio
    async def test_owner_header_platform_admin_is_400(self, client):
        for route in ROUTES:
            result = await call(client, route, token("Super Admin", "platform-admin"), header="platform-admin")
            assert result.status == 400, route
            assert result.json["detail"].startswith("Select a tenant"), route
            assert_no_figure(result)

    @pytest.mark.asyncio
    async def test_owner_header_reads_only_that_tenant_everywhere(self, client):
        owner = token("Super Admin", "platform-admin")
        for tenant in TENANTS:
            for route in ROUTES:
                result = await call(client, route, owner, header=tenant, id_of=tenant)
                assert_own(route, result, tenant)
                assert_no_foreign(result, tenant)

    @pytest.mark.asyncio
    async def test_support_header_is_ignored(self, client):
        support = token("platform_support", "platform-admin")
        for route in ROUTES:
            result = await call(client, route, support, header="tenant-a")
            assert result.status == (403 if route in REPORT_ROUTES else 400), route
            assert_no_figure(result)

    @pytest.mark.asyncio
    async def test_billing_is_refused(self, client):
        for header in (None, "tenant-a"):
            for route in ROUTES:
                result = await call(client, route, token("platform_billing", "platform-admin"), header=header)
                assert result.status == 403, route
                assert_no_figure(result)


class TestIdenticalLookingTenants:
    @pytest.mark.asyncio
    async def test_seed_really_is_identical_across_tenants(self, two_tenants):
        shape = {"name", "assetTag", "serialNumber", "modelId"}
        docs = {t: sorted(
            [{k: d.get(k) for k in shape} async for d in two_tenants.assets.find({"tenantId": t})],
            key=repr) for t in TENANTS}
        assert docs["tenant-a"] == docs["tenant-b"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tenant", TENANTS)
    async def test_identical_looking_assets_stay_separate(self, client, tenant):
        bearer = token("admin", tenant)
        ids = _ids(tenant)
        summary = (await call(client, "summary", bearer)).json["coverage"]
        assert summary["flags"]["possibleDuplicate"] == 2 and summary["possibleDuplicatePairs"] == 1
        rows = {r["assetId"]: r for r in (await call(client, "assets", bearer)).json["items"]}
        assert rows[ids[0]]["possibleDuplicateOf"] == [ids[2]]
        assert rows[ids[2]]["possibleDuplicateOf"] == [ids[0]]
        assert rows[ids[1]]["possibleDuplicateOf"] == []
        for row in rows.values():
            assert set(row["possibleDuplicateOf"]) <= set(ids)
        detail = (await call(client, "asset_detail", bearer, id_of=tenant)).json
        assert detail["possibleDuplicateOf"] == [ids[2]]


class TestConcurrency:
    @pytest.mark.asyncio
    async def test_concurrent_requests_do_not_mix(self, client):
        admin_a, admin_b = token("admin", "tenant-a"), token("admin", "tenant-b")
        owner = token("Super Admin", "platform-admin")
        for _ in range(10):
            jobs = [
                call(client, "summary", admin_a), call(client, "summary", admin_b),
                call(client, "summary", owner, header="tenant-b"), call(client, "summary", owner, header="tenant-a"),
                call(client, "kpis", admin_a), call(client, "kpis", admin_b),
                call(client, "kpis", owner, header="tenant-b"), call(client, "kpis", owner, header="tenant-a"),
            ]
            results = await asyncio.gather(*jobs)
            expected = ["tenant-a", "tenant-b", "tenant-b", "tenant-a"] * 2
            for index, (result, tenant) in enumerate(zip(results, expected)):
                assert_own("summary" if index < 4 else "kpis", result, tenant)
                assert_no_foreign(result, tenant)
