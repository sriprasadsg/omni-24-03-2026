"""Two-tenant proof for the seven custom report routes (Phase 78, plan 78-12, gap G-78-WR02, D-13 amended
2026-11-17). Real MongoDB (skipped without one, and a skip is a failed gate), the real TenantMiddleware, real
signed session tokens, and the real route guards and tenant resolver.

Value: protects=a Platform Owner who chooses an organization with X-Tenant-ID saves, lists, previews, runs,
exports and deletes custom reports of that organization only (never a blend of all of them, including the
Book Value column), and a tenant user never sees another tenant's rows or saved definitions, even when both
tenants hold assets with identical names, tags and serial numbers under the same model id; fails_when=a
custom report response carries the other tenant's asset id, definition name, cost or book value, an Owner
without a chosen tenant gets a figure or a definition list instead of 400, Support or Billing gets a figure,
or concurrent requests for two tenants mix their results; no_claim=the browser, the Reports tab, and the
formulas (the 78-01..78-05 suites own those).

Nothing here replaces authentication, the permission check, the resolver or the per-request tenant: the token
check that resets the per-request tenant to the token's own tenant after the middleware applied the Owner's
choice is exactly what the shared resolver exists to defeat (RESEARCH Pitfall 1).
"""
import asyncio
import csv
import io
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
import itam_reporting_endpoints
import itam_reporting_service
import rbac_utils
from authentication_service import create_access_token
from itam_finance_service import compute_book_value
from itam_reporting_filters import list_report_fields
from tenant_middleware import TenantMiddleware

FIXED_NOW = datetime(2026, 11, 16, 12, 0, 0, tzinfo=timezone.utc)
PURCHASE = (FIXED_NOW - timedelta(days=400)).isoformat()

BASE = "/api/itam/reports/custom"
COSTS = "/api/itam/costs/assets"

TENANTS = ("tenant-a", "tenant-b")
# Same names, tags, serial numbers and model id in both tenants; only ids, costs and the policy differ.
SHAPES = (
    {"name": "Laptop One", "tag": "TAG-100", "serial": "SER-0001"},
    {"name": "Server Two", "tag": "TAG-200", "serial": "SER-0002"},
)
DATA = {
    "tenant-a": {"key": "a", "costs": (120000, 54321), "life": 3, "salvage": 10000},
    "tenant-b": {"key": "b", "costs": (345600, 87650), "life": 4, "salvage": 0},
}
COLUMNS = ["asset.assetTag", "asset.name", "finance.bookValueCents"]
SAVE_BODY = {"name": "Owner saved", "columns": ["asset.assetTag"], "filters": []}

_LABELS = {f["key"]: f["label"] for f in list_report_fields()}
TAG, NAME, BOOK = (_LABELS[k] for k in COLUMNS)


def _books(tenant):
    d = DATA[tenant]
    return [compute_book_value(PURCHASE, c, d["life"], d["salvage"], FIXED_NOW)["bookValueCents"] for c in d["costs"]]


def _other(tenant):
    return TENANTS[1] if tenant == TENANTS[0] else TENANTS[0]


def _rpt(tenant):
    return f"rpt-{DATA[tenant]['key']}"


def _def_name(tenant):
    return f"Book values {DATA[tenant]['key']}"


def _leaves(node):
    if isinstance(node, dict):
        for value in node.values():
            yield from _leaves(value)
    elif isinstance(node, list):
        for value in node:
            yield from _leaves(value)
    else:
        yield node


def _foreign(tenant):
    """What only the other tenant owns: its id fragments, definition name, costs and book values."""
    o = _other(tenant)
    return {
        "strings": [f"{DATA[o]['key']}-asset-", _def_name(o), o],
        "numbers": {*DATA[o]["costs"], *_books(o)},
    }


def token(role, tenant, sub=None):
    return create_access_token({"sub": sub or f"{role}@{tenant}", "role": role, "tenant_id": tenant, "mfa_verified": True})


@pytest.fixture(autouse=True)
def _fixed_clock(monkeypatch):
    monkeypatch.setattr(itam_cost_service, "utc_now", lambda: FIXED_NOW)


@pytest.fixture(autouse=True)
def _reports_dir_untouched():
    """Export files this module creates are removed (also by the helper that reads them)."""
    directory = itam_reporting_service._REPORTS_DIR
    before = set(os.listdir(directory)) if os.path.isdir(directory) else set()
    yield
    for name in set(os.listdir(directory)) - before:
        os.remove(os.path.join(directory, name))


@pytest_asyncio.fixture
async def seeded(mongo_db):
    for tenant in TENANTS:
        d = DATA[tenant]
        await mongo_db.asset_models.insert_one(
            {"tenantId": tenant, "id": "model-std", "usefulLifeYears": d["life"], "salvageValueCents": d["salvage"]})
        await mongo_db.assets.insert_many([
            {"tenantId": tenant, "id": f"{d['key']}-asset-{i + 1}", "name": s["name"], "assetTag": s["tag"],
             "serialNumber": s["serial"], "lifecycleStatus": "deployed", "modelId": "model-std",
             "purchaseCostCents": d["costs"][i], "purchaseDate": PURCHASE}
            for i, s in enumerate(SHAPES)
        ])
        await mongo_db.itam_reports.insert_one(
            {"tenantId": tenant, "id": _rpt(tenant), "name": _def_name(tenant), "columns": COLUMNS, "filters": [],
             "createdAt": "2026-11-16T09:00:00.000+00:00", "createdBy": f"seed@{tenant}"})
    return mongo_db


@pytest.fixture
def app(monkeypatch, seeded):
    # The role store the permission check reads is the same throwaway database, so a role outside the
    # built-in table is refused on its merits and not because no database is connected.
    for module in (itam_cost_endpoints, itam_reporting_endpoints, itam_reporting_service, rbac_utils):
        monkeypatch.setattr(module, "get_database", lambda: database.TenantIsolatedDatabase(seeded))
    application = FastAPI()
    application.add_middleware(TenantMiddleware)
    for module in (itam_cost_endpoints, itam_reporting_endpoints):
        application.include_router(module.router)
    return application


@pytest_asyncio.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


def _headers(bearer, header=None):
    return {"Authorization": f"Bearer {bearer}", **({"X-Tenant-ID": header} if header is not None else {})}


ROUTES = ("save", "list", "preview", "get", "delete", "run", "export")


class Result:
    """A response plus, for an export, the CSV rows read from the file it wrote (the file is removed at once)."""

    def __init__(self, response, csv_rows=None, csv_text=""):
        self.status_code = response.status_code
        self.text = response.text + csv_text
        self.csv_rows = csv_rows or []
        self._response = response

    def json(self):
        return self._response.json()


async def call(client, route, bearer, *, header=None, report_id="rpt-a"):
    """One request to one custom report route; the export is read back from its file and the file removed."""
    h = _headers(bearer, header)
    url = f"{BASE}/{report_id}"
    if route == "save":
        return Result(await client.post(BASE, headers=h, json=SAVE_BODY))
    if route == "list":
        return Result(await client.get(BASE, headers=h))
    if route == "preview":
        return Result(await client.post(f"{BASE}/preview", headers=h, json={**SAVE_BODY, "columns": COLUMNS}))
    if route == "get":
        return Result(await client.get(url, headers=h))
    if route == "delete":
        return Result(await client.delete(url, headers=h))
    if route == "run":
        return Result(await client.post(f"{url}/run", headers=h))
    response = await client.post(f"{url}/export", params={"format": "csv"}, headers=h)
    if response.status_code != 200:
        return Result(response)
    path = os.path.join(itam_reporting_service._REPORTS_DIR, response.json()["filename"])
    try:
        with open(path, encoding="utf-8", newline="") as handle:
            text = handle.read()
    finally:
        os.remove(path)
    return Result(response, list(csv.DictReader(io.StringIO(text))), text)


def assert_own_rows(result, tenant):
    """The run answered 200 with exactly this tenant's two assets and this tenant's own book values."""
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["rowCount"] == 2
    assert {row[TAG] for row in body["rows"]} == {"TAG-100", "TAG-200"}
    assert sorted(row[BOOK] for row in body["rows"]) == sorted(_books(tenant))
    assert not (set(_leaves(body)) & _foreign(tenant)["numbers"])


def assert_own_export(result, tenant):
    assert result.status_code == 200, result.text
    assert result.json()["rowCount"] == 2
    assert {row[TAG] for row in result.csv_rows} == {"TAG-100", "TAG-200"}
    assert sorted(int(row[BOOK]) for row in result.csv_rows) == sorted(_books(tenant))


def assert_no_figure(result):
    """A refused response carries no id, definition name, cost or book value of either tenant."""
    for tenant in TENANTS:
        for needle in _foreign(tenant)["strings"]:
            assert needle not in result.text
    try:
        body = result.json()
    except ValueError:
        return
    for tenant in TENANTS:
        assert not (set(_leaves(body)) & _foreign(tenant)["numbers"])


def assert_own(route, result, tenant):
    """A 200 (201 for save, 204 for delete) answer made of this tenant's data only."""
    if route == "run" or route == "preview":
        assert_own_rows(result, tenant)
    elif route == "export":
        assert_own_export(result, tenant)
    elif route == "list":
        assert result.status_code == 200, result.text
        assert [d["name"] for d in result.json()] == [_def_name(tenant)]
    elif route == "get":
        assert result.status_code == 200, result.text
        assert result.json()["id"] == _rpt(tenant) and result.json()["tenantId"] == tenant
    elif route == "save":
        assert result.status_code == 201, result.text
        assert result.json()["tenantId"] == tenant
    else:
        assert result.status_code == 204, result.text


class TestSavedRunTracer:
    @pytest.mark.asyncio
    async def test_owner_without_tenant_is_400(self, client):
        assert _books("tenant-a") != _books("tenant-b")
        owner = token("Super Admin", "platform-admin")
        response = await call(client, "run", owner)
        assert response.status_code == 400
        assert response.json()["detail"].startswith("Select a tenant")
        assert_no_figure(response)

    @pytest.mark.asyncio
    async def test_owner_with_tenant_runs_only_that_tenant(self, client):
        owner = token("Super Admin", "platform-admin")
        for tenant in TENANTS:
            assert_own_rows(await call(client, "run", owner, header=tenant, report_id=_rpt(tenant)), tenant)

    @pytest.mark.asyncio
    async def test_tenant_admin_runs_own_and_not_foreign_definition(self, client):
        for tenant in TENANTS:
            admin = token("admin", tenant)
            assert_own_rows(await call(client, "run", admin, report_id=_rpt(tenant)), tenant)
            assert (await call(client, "run", admin, report_id=_rpt(_other(tenant)))).status_code == 404


class TestOwnerChoosesTenant:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("header", (None, "platform-admin"))
    async def test_owner_without_a_real_tenant_is_400_everywhere(self, client, seeded, header):
        owner = token("Super Admin", "platform-admin")
        for route in ROUTES:
            result = await call(client, route, owner, header=header)
            assert result.status_code == 400, route
            assert result.json()["detail"].startswith("Select a tenant"), route
            assert_no_figure(result)
        for tenant in TENANTS:  # the refused delete and save left both definitions as they were
            names = [d["name"] async for d in seeded.itam_reports.find({"tenantId": tenant})]
            assert names == [_def_name(tenant)]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tenant", TENANTS)
    async def test_owner_with_tenant_covers_only_that_tenant(self, client, tenant):
        owner = token("Super Admin", "platform-admin")
        for route in ("list", "get", "preview", "run", "export"):
            result = await call(client, route, owner, header=tenant, report_id=_rpt(tenant))
            assert_own(route, result, tenant)
            for needle in _foreign(tenant)["strings"]:
                assert needle not in result.text, f"{needle!r} leaked into {route}"

    @pytest.mark.asyncio
    async def test_owner_export_record_and_file_belong_to_the_chosen_tenant(self, client, seeded):
        owner = token("Super Admin", "platform-admin")
        result = await call(client, "export", owner, header="tenant-b", report_id="rpt-b")
        assert_own_export(result, "tenant-b")
        record = await seeded.itam_report_exports.find_one({"filename": result.json()["filename"]})
        assert record["tenantId"] == "tenant-b"

    @pytest.mark.asyncio
    async def test_owner_save_lands_in_the_chosen_tenant_and_is_shared_there(self, client, seeded):
        owner = token("Super Admin", "platform-admin")
        saved = await call(client, "save", owner, header="tenant-b")
        assert saved.status_code == 201 and saved.json()["tenantId"] == "tenant-b"
        raw = await seeded.itam_reports.find_one({"id": saved.json()["id"]})
        assert raw["tenantId"] == "tenant-b" and raw["createdBy"] == "Super Admin@platform-admin"
        listed_b = {d["name"] for d in (await call(client, "list", token("admin", "tenant-b"))).json()}
        listed_a = {d["name"] for d in (await call(client, "list", token("admin", "tenant-a"))).json()}
        assert "Owner saved" in listed_b and "Owner saved" not in listed_a
        assert await seeded.itam_reports.count_documents({"tenantId": "platform-admin"}) == 0


class TestForeignDefinitions:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("actor", ("owner", "admin"))
    async def test_foreign_and_unknown_ids_look_alike_and_nothing_is_deleted(self, client, seeded, actor):
        bearer = token("Super Admin", "platform-admin") if actor == "owner" else token("admin", "tenant-a")
        header = "tenant-a" if actor == "owner" else None
        for route in ("get", "run", "export", "delete"):
            foreign = await call(client, route, bearer, header=header, report_id="rpt-b")
            unknown = await call(client, route, bearer, header=header, report_id="rpt-missing")
            assert foreign.status_code == unknown.status_code == 404, route
            assert foreign._response.content == unknown._response.content, route
        assert await seeded.itam_reports.count_documents({"id": "rpt-b"}) == 1

    @pytest.mark.asyncio
    async def test_a_tenant_admin_deletes_only_its_own_definition(self, client, seeded):
        assert (await call(client, "delete", token("admin", "tenant-b"), report_id="rpt-b")).status_code == 204
        assert await seeded.itam_reports.count_documents({"id": "rpt-b"}) == 0
        assert await seeded.itam_reports.count_documents({"id": "rpt-a"}) == 1


class TestTenantUsersAndPlatformRoles:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("tenant", TENANTS)
    async def test_tenant_admin_header_spoof_is_ignored(self, client, tenant):
        admin = token("admin", tenant)
        for route in ("list", "get", "preview", "run", "export", "save", "delete"):
            result = await call(client, route, admin, header=_other(tenant), report_id=_rpt(tenant))
            assert_own(route, result, tenant)
            if route not in ("save", "delete"):
                for needle in _foreign(tenant)["strings"]:
                    assert needle not in result.text

    @pytest.mark.asyncio
    @pytest.mark.parametrize("header", (None, "tenant-a"))
    async def test_support_gets_400_on_reads_and_403_on_the_rest(self, client, header):
        support = token("platform_support", "platform-admin")
        for route in ROUTES:
            result = await call(client, route, support, header=header)
            assert result.status_code == (400 if route in ("list", "get") else 403), route
            assert_no_figure(result)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("header", (None, "tenant-a"))
    async def test_billing_is_refused_everywhere(self, client, header):
        for route in ROUTES:
            result = await call(client, route, token("platform_billing", "platform-admin"), header=header)
            assert result.status_code == 403, route
            assert_no_figure(result)


class TestConcurrencyAndParity:
    @pytest.mark.asyncio
    async def test_concurrent_requests_do_not_mix(self, client):
        admin_a, admin_b = token("admin", "tenant-a"), token("admin", "tenant-b")
        owner = token("Super Admin", "platform-admin")
        actors = [(admin_a, None, "tenant-a"), (admin_b, None, "tenant-b"),
                  (owner, "tenant-b", "tenant-b"), (owner, "tenant-a", "tenant-a")]
        for _ in range(10):
            jobs = [call(client, route, bearer, header=header, report_id=_rpt(tenant))
                    for route in ("run", "list") for bearer, header, tenant in actors]
            results = await asyncio.gather(*jobs)
            for index, result in enumerate(results):
                tenant = actors[index % 4][2]
                assert_own("run" if index < 4 else "list", result, tenant)
                for needle in _foreign(tenant)["strings"]:
                    assert needle not in result.text

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tenant", TENANTS)
    async def test_custom_book_value_equals_the_cost_list(self, client, tenant):
        admin = token("admin", tenant)
        run = (await call(client, "run", admin, report_id=_rpt(tenant))).json()
        costs = (await client.get(COSTS, headers=_headers(admin))).json()
        by_tag = {item["assetTag"]: item["bookValueCents"] for item in costs["items"]}
        assert {row[TAG]: row[BOOK] for row in run["rows"]} == by_tag
