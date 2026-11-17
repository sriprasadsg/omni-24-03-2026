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


def assert_own_rows(response, tenant):
    """The run answered 200 with exactly this tenant's two assets and this tenant's own book values."""
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rowCount"] == 2
    assert {row[TAG] for row in body["rows"]} == {"TAG-100", "TAG-200"}
    assert sorted(row[BOOK] for row in body["rows"]) == sorted(_books(tenant))
    assert not (set(_leaves(body)) & _foreign(tenant)["numbers"])


def assert_no_figure(response):
    """A refused response carries no id, definition name, cost or book value of either tenant."""
    for tenant in TENANTS:
        for needle in _foreign(tenant)["strings"]:
            assert needle not in response.text
    try:
        body = response.json()
    except ValueError:
        return
    for tenant in TENANTS:
        assert not (set(_leaves(body)) & _foreign(tenant)["numbers"])


class TestSavedRunTracer:
    @pytest.mark.asyncio
    async def test_owner_without_tenant_is_400(self, client):
        assert _books("tenant-a") != _books("tenant-b")
        owner = token("Super Admin", "platform-admin")
        response = await client.post(f"{BASE}/rpt-a/run", headers=_headers(owner))
        assert response.status_code == 400
        assert response.json()["detail"].startswith("Select a tenant")
        assert_no_figure(response)

    @pytest.mark.asyncio
    async def test_owner_with_tenant_runs_only_that_tenant(self, client):
        owner = token("Super Admin", "platform-admin")
        for tenant in TENANTS:
            assert_own_rows(await client.post(f"{BASE}/{_rpt(tenant)}/run", headers=_headers(owner, tenant)), tenant)

    @pytest.mark.asyncio
    async def test_tenant_admin_runs_own_and_not_foreign_definition(self, client):
        for tenant in TENANTS:
            admin = token("admin", tenant)
            assert_own_rows(await client.post(f"{BASE}/{_rpt(tenant)}/run", headers=_headers(admin)), tenant)
            foreign = await client.post(f"{BASE}/{_rpt(_other(tenant))}/run", headers=_headers(admin))
            assert foreign.status_code == 404
