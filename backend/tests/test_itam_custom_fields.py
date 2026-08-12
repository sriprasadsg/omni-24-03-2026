"""Custom Fields Manager tests — Phase 65 Plan 01 (ITAM-DAT-01).

Reuses the same hand-rolled MockTenantIsolatedCollection/Database fake-db convention as
test_itam_catalog.py (56-02) rather than inventing a second style — see that file's fixture
comments for why proxy methods are real `async def` functions and why patches target each
importing module's own bound name, not the source module's attribute.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

from tests.conftest import make_test_app, make_token_data, _make_col
from authentication_service import get_current_user as real_get_current_user


class MockTenantIsolatedCollection:
    """Same shape as test_itam_catalog.py's — real `async def` proxy methods (a single
    await chain), never AsyncMock(side_effect=lambda ...) wrapping another AsyncMock, which
    calls the inner AsyncMock without awaiting it and returns a live never-awaited coroutine
    instead of the real value."""

    def __init__(self, collection_name, tenant_id, raw_collection_mock):
        self._collection_name = collection_name
        self._tenant_id = tenant_id
        self._raw_collection = raw_collection_mock

        async def _find_one(f, *args, **kwargs):
            return await raw_collection_mock.find_one({**f, "tenantId": self._tenant_id}, *args, **kwargs)

        async def _insert_one(doc, *args, **kwargs):
            return await raw_collection_mock.insert_one({**doc, "tenantId": self._tenant_id}, *args, **kwargs)

        async def _count_documents(f, *args, **kwargs):
            return await raw_collection_mock.count_documents({**f, "tenantId": self._tenant_id}, *args, **kwargs)

        async def _find_one_and_update(f, u, *args, **kwargs):
            return await raw_collection_mock.find_one_and_update({**f, "tenantId": self._tenant_id}, u, *args, **kwargs)

        async def _delete_one(f, *args, **kwargs):
            return await raw_collection_mock.delete_one({**f, "tenantId": self._tenant_id}, *args, **kwargs)

        self.find_one = _find_one
        self.insert_one = _insert_one
        self.count_documents = _count_documents
        self.find_one_and_update = _find_one_and_update
        self.delete_one = _delete_one
        self.find = MagicMock(side_effect=lambda f=None, *args, **kwargs:
                              raw_collection_mock.find({**(f if f else {}), "tenantId": self._tenant_id}, *args, **kwargs))


class MockTenantIsolatedDatabase:
    def __init__(self, raw_db_mock, tenant_id):
        self._raw_db = raw_db_mock
        self._tenant_id = tenant_id

    def __getattr__(self, name):
        return MockTenantIsolatedCollection(name, self._tenant_id, getattr(self._raw_db, name))

    def __getitem__(self, name):
        return self.__getattr__(name)


CATALOG_COLLECTIONS = ("assets", "manufacturers", "asset_categories", "locations", "suppliers", "asset_models", "counters")


@pytest.fixture
def mock_db():
    """Basic mock database with every collection this plan's kinds touch."""
    db = MagicMock()
    for name in CATALOG_COLLECTIONS:
        setattr(db, name, _make_col())
    return db


@pytest.fixture(autouse=True)
def patch_get_database_globally(mock_db, monkeypatch):
    """Patch get_database globally to return our mock wrapped for tenant isolation.

    itam_catalog_endpoints.py does `from database import get_database` (name-binding
    import), so patching database.get_database alone does not affect its already-bound
    local reference — the importing module's own name must be patched too.
    """
    import database
    import itam_catalog_endpoints
    _current_tenant_id = "default-tenant"

    def get_mock_tenant_db():
        return MockTenantIsolatedDatabase(mock_db, _current_tenant_id)

    def _patch_all():
        monkeypatch.setattr(database, "get_database", get_mock_tenant_db)
        monkeypatch.setattr(itam_catalog_endpoints, "get_database", get_mock_tenant_db)

    _patch_all()

    def set_current_tenant_id(tenant_id):
        nonlocal _current_tenant_id
        _current_tenant_id = tenant_id
        _patch_all()

    return set_current_tenant_id


@pytest.fixture
def itam_app(mock_db, patch_get_database_globally, monkeypatch):
    """Test FastAPI app mounting only the catalog router — this plan touches no asset route."""
    import itam_catalog_endpoints

    monkeypatch.setattr(itam_catalog_endpoints, "verify_permission", AsyncMock(return_value=True))

    app, _ = make_test_app(itam_catalog_endpoints.router)
    return app


def _wire_crud_store(col):
    """Wire a raw collection mock with a simple in-memory list-backed store supporting
    insert_one/find_one/find/find_one_and_update/delete_one/count_documents, matching
    exactly what MockTenantIsolatedCollection forwards (filters already carry tenantId).
    Returns the backing list so a test can seed fixture documents directly."""
    store: list = []

    async def _insert_one(doc):
        store.append(dict(doc))
        return MagicMock(inserted_id=doc.get("id"))

    async def _find_one(f, *a, **kw):
        for d in store:
            if all(d.get(k) == v for k, v in f.items()):
                return dict(d)
        return None

    def _find(f=None, *a, **kw):
        f = f or {}
        matched = [dict(d) for d in store if all(d.get(k) == v for k, v in f.items())]
        cursor = MagicMock()
        cursor.limit = MagicMock(return_value=cursor)
        cursor.to_list = AsyncMock(side_effect=lambda length=None: matched)
        return cursor

    async def _find_one_and_update(f, u, *a, return_document=None, **kw):
        for d in store:
            if all(d.get(k) == v for k, v in f.items()):
                d.update(u.get("$set", {}))
                return dict(d)
        return None

    async def _delete_one(f, *a, **kw):
        for i, d in enumerate(store):
            if all(d.get(k) == v for k, v in f.items()):
                store.pop(i)
                return MagicMock(deleted_count=1)
        return MagicMock(deleted_count=0)

    async def _count_documents(f, *a, **kw):
        return sum(1 for d in store if all(d.get(k) == v for k, v in f.items()))

    col.insert_one = AsyncMock(side_effect=_insert_one)
    col.find_one = AsyncMock(side_effect=_find_one)
    col.find = MagicMock(side_effect=_find)
    col.find_one_and_update = AsyncMock(side_effect=_find_one_and_update)
    col.delete_one = AsyncMock(side_effect=_delete_one)
    col.count_documents = AsyncMock(side_effect=_count_documents)
    return store


def _authed_client_kwargs(itam_app, patch_get_database_globally, tenant_id="tenant-a", role="admin"):
    current_user = make_token_data(tenant_id=tenant_id, role=role)
    patch_get_database_globally(tenant_id)
    itam_app.dependency_overrides[real_get_current_user] = lambda: current_user


class TestGetAssetModelFields:
    """Task 1: GET /models/{model_id}/fields."""

    @pytest.mark.asyncio
    async def test_flattens_fieldsets_in_declaration_order(self, mock_db, itam_app, patch_get_database_globally):
        model_store = _wire_crud_store(mock_db.asset_models)
        model_store.append({
            "id": "model-1",
            "name": "ThinkPad X1",
            "tenantId": "tenant-a",
            "fieldsets": [
                {"name": "Hardware", "fields": [
                    {"key": "ramGb", "label": "RAM (GB)", "type": "number"},
                    {"key": "hasTouchscreen", "label": "Touchscreen", "type": "boolean"},
                ]},
                {"name": "Warranty", "fields": [
                    {"key": "warrantyTier", "label": "Warranty Tier", "type": "select", "options": ["basic", "premium"]},
                ]},
            ],
        })
        _authed_client_kwargs(itam_app, patch_get_database_globally)

        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/itam/catalog/models/model-1/fields")
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["modelId"] == "model-1"
            assert data["modelName"] == "ThinkPad X1"
            assert [f["key"] for f in data["fields"]] == ["ramGb", "hasTouchscreen", "warrantyTier"]
            assert data["fields"][0]["fieldsetName"] == "Hardware"
            assert data["fields"][2]["fieldsetName"] == "Warranty"
            assert data["usageCounts"] == {}

    @pytest.mark.asyncio
    async def test_unknown_model_id_returns_404(self, mock_db, itam_app, patch_get_database_globally):
        _wire_crud_store(mock_db.asset_models)
        _authed_client_kwargs(itam_app, patch_get_database_globally)

        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/itam/catalog/models/does-not-exist/fields")
            assert r.status_code == 404, r.text
