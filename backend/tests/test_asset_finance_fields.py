"""D-04 / D-10: asset reads hide purchase and warranty fields from callers without view:itam.

Exercises GET /api/assets, /api/assets/search and /api/assets/{id} through the real
handlers (asset_endpoints.router mounted alone, fake collection returning the stored
documents by reference so any in-place mutation is visible).
"""
import copy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import rbac_defaults
import rbac_utils
import cache_service
from auth_types import TokenData
from authentication_service import get_current_user
from database import get_database

FINANCE_KEYS = [
    "purchaseCostCents", "purchaseDate", "poNumber", "purchase_order_id", "supplierId",
    "warrantyMonths", "warranty_expiry_date", "warrantyAlertSentAt", "salvage_value",
    "useful_life_years", "bookValueCents", "currentBookValueCents",
]
PLAIN = {"id": "a1", "tenantId": "t1", "hostname": "host-1", "name": "Laptop 1", "status": "Online"}


def _asset():
    doc = dict(PLAIN)
    doc.update({
        "purchaseCostCents": 120000, "purchaseDate": "2024-01-01", "poNumber": "PO-9",
        "purchase_order_id": "po-1", "supplierId": "sup-1", "warrantyMonths": 36,
        "warranty_expiry_date": "2027-01-01", "warrantyAlertSentAt": "2026-12-01",
        "salvage_value": 10.0, "useful_life_years": 4, "bookValueCents": 90000,
        "currentBookValueCents": 80000,
    })
    return doc


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    def skip(self, _n):
        return self

    def limit(self, _n):
        return self

    def sort(self, _spec):
        return self

    async def to_list(self, length=None):
        return self._docs


class _Collection:
    def __init__(self, docs):
        self.docs = docs

    async def count_documents(self, _q):
        return len(self.docs)

    def find(self, *_a, **_k):
        return _Cursor(self.docs)

    async def find_one(self, *_a, **_k):
        return self.docs[0] if self.docs else None


class _Db:
    def __init__(self, docs):
        self.assets = _Collection(docs)
        self.agents = _Collection([])

    def __getitem__(self, name):
        return getattr(self, name)


class _RefCache:
    """Worst-case cache: hands back the very object that was stored."""
    enabled = True

    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ttl=None):
        self.store[key] = value
        return True

    def delete_pattern(self, _p):
        self.store.clear()


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    perms = {}

    async def _defaults_only(db, role, tenant_id):
        if role in perms:
            return list(perms[role])
        return list(rbac_defaults.defaults_for(rbac_utils._rbac_service._normalize_role(role or "")))

    monkeypatch.setattr(rbac_utils, "granted_permissions", _defaults_only)
    monkeypatch.setattr(rbac_utils, "get_database", lambda: None)
    monkeypatch.setattr(cache_service, "cache", _RefCache())
    return perms


@pytest.fixture
def stored():
    return [_asset()]


def _client(stored, role, username="u@example.com"):
    import asset_endpoints

    app = FastAPI()
    app.include_router(asset_endpoints.router)
    user = TokenData(username=username, role=role, tenant_id="t1")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_database] = lambda: _Db(stored)
    return TestClient(app)


def _items(resp):
    body = resp.json()
    return body["items"] if isinstance(body, dict) and "items" in body else body


def _has_finance(doc):
    return [k for k in FINANCE_KEYS if k in doc]


def test_non_itam_list_omits_finance_fields(stored):
    resp = _client(stored, "viewer").get("/api/assets")
    assert resp.status_code == 200
    item = _items(resp)[0]
    assert _has_finance(item) == []
    assert item["hostname"] == "host-1" and item["status"] == "Online"


def test_non_itam_search_omits_finance_fields(stored):
    resp = _client(stored, "viewer").get("/api/assets/search", params={"q": "host"})
    assert resp.status_code == 200
    assert _has_finance(resp.json()[0]) == []
    assert resp.json()[0]["hostname"] == "host-1"


def test_non_itam_detail_omits_finance_fields(stored):
    resp = _client(stored, "viewer").get("/api/assets/a1")
    assert resp.status_code == 200
    assert _has_finance(resp.json()) == []
    assert resp.json()["name"] == "Laptop 1"


@pytest.mark.parametrize("role", ["itam_viewer", "itam_admin", "Super Admin", "admin"])
def test_itam_callers_keep_finance_fields(stored, role):
    # view:itam (itam_viewer), manage:itam (itam_admin, D-03 twin), super admin, tenant admin
    client = _client(stored, role)
    expected = _asset()
    assert {k: _items(client.get("/api/assets"))[0][k] for k in FINANCE_KEYS} == {k: expected[k] for k in FINANCE_KEYS}
    assert _has_finance(client.get("/api/assets/search", params={"q": "host"}).json()[0]) == FINANCE_KEYS
    assert _has_finance(client.get("/api/assets/a1").json()) == FINANCE_KEYS


def test_stripping_never_mutates_the_source_documents(stored):
    before = copy.deepcopy(stored)
    client = _client(stored, "viewer")
    client.get("/api/assets")
    client.get("/api/assets/search", params={"q": "host"})
    client.get("/api/assets/a1")
    for key in FINANCE_KEYS:
        assert stored[0][key] == before[0][key], key
    assert _has_finance(_items(_client(stored, "itam_viewer").get("/api/assets"))[0]) == FINANCE_KEYS


def test_cached_results_do_not_cross_callers(stored):
    viewer = _client(stored, "viewer")
    itam = _client(stored, "itam_viewer", username="itam@example.com")
    first = _items(viewer.get("/api/assets"))[0]
    second = _items(viewer.get("/api/assets"))[0]  # served from the cache
    assert _has_finance(first) == [] and _has_finance(second) == []
    assert cache_service.cache.store, "the second call must have been served from the cache"
    assert _has_finance(_items(itam.get("/api/assets"))[0]) == FINANCE_KEYS
    assert _has_finance(_items(viewer.get("/api/assets"))[0]) == []


def test_role_edit_takes_effect_before_the_cache_expires(stored, _env):
    # Same user, same cache key, permissions change between calls (RESEARCH A5).
    _env["custom"] = ["view:assets"]
    client = _client(stored, "custom", username="c@example.com")
    assert _has_finance(_items(client.get("/api/assets"))[0]) == []
    _env["custom"] = ["view:assets", "view:itam"]
    assert _has_finance(_items(client.get("/api/assets"))[0]) == FINANCE_KEYS
    _env["custom"] = ["view:assets"]
    assert _has_finance(_items(client.get("/api/assets"))[0]) == []


def test_helper_builds_new_objects():
    from asset_finance_fields import ASSET_FINANCE_FIELDS, strip_finance, strip_finance_many

    assert set(FINANCE_KEYS) <= set(ASSET_FINANCE_FIELDS)
    doc = _asset()
    out = strip_finance(doc)
    assert out is not doc and _has_finance(out) == [] and _has_finance(doc) == FINANCE_KEYS
    many = [doc]
    out_many = strip_finance_many(many)
    assert out_many is not many and out_many[0] is not doc and _has_finance(many[0]) == FINANCE_KEYS
    assert strip_finance(None) is None
