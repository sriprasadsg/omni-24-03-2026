"""Catalog expansion tests — Phase 56 Plan 02.

Covers CRUD/tenant/delete-guard coverage for Category, Location, and Supplier. Reuses the
hand-rolled MockTenantIsolatedCollection/Database fake-db convention established in
test_itam_foundation.py (56-01) rather than inventing a second style — see that file's
fixture comments for why proxy methods are real `async def` functions and why patches target
each importing module's own bound name, not the source module's attribute.
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
    """Same shape as test_itam_foundation.py's — real `async def` proxy methods (a single
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


CATALOG_COLLECTIONS = ("assets", "manufacturers", "asset_categories", "locations", "suppliers", "counters")


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


class TestCategoryLocationSupplier:
    """Task 1: Category, Location, and Supplier registered as catalog kinds."""

    @pytest.mark.asyncio
    async def test_create_and_read_category(self, mock_db, itam_app, patch_get_database_globally):
        _wire_crud_store(mock_db.asset_categories)
        _authed_client_kwargs(itam_app, patch_get_database_globally)

        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/itam/catalog/categories", json={"name": "Laptops"})
            assert r.status_code == 201, r.text
            cid = r.json()["id"]

            r2 = await ac.get(f"/api/itam/catalog/categories/{cid}")
            assert r2.status_code == 200, r2.text
            assert r2.json()["name"] == "Laptops"

    @pytest.mark.asyncio
    async def test_create_and_read_location(self, mock_db, itam_app, patch_get_database_globally):
        _wire_crud_store(mock_db.locations)
        _authed_client_kwargs(itam_app, patch_get_database_globally)

        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/itam/catalog/locations", json={"name": "HQ - Building A"})
            assert r.status_code == 201, r.text
            lid = r.json()["id"]

            r2 = await ac.get(f"/api/itam/catalog/locations/{lid}")
            assert r2.status_code == 200, r2.text
            assert r2.json()["name"] == "HQ - Building A"

    @pytest.mark.asyncio
    async def test_create_supplier_with_contact_fields(self, mock_db, itam_app, patch_get_database_globally):
        _wire_crud_store(mock_db.suppliers)
        _authed_client_kwargs(itam_app, patch_get_database_globally)

        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/itam/catalog/suppliers", json={
                "name": "Acme Supply Co",
                "contactName": "Jane Doe",
                "contactEmail": "jane@example.com",
                "contactPhone": "555-1234",
                "website": "https://acme.example.com",
                "address": "123 Main St",
            })
            assert r.status_code == 201, r.text
            data = r.json()
            assert data["contactName"] == "Jane Doe"
            assert data["contactEmail"] == "jane@example.com"
            assert data["contactPhone"] == "555-1234"
            assert data["website"] == "https://acme.example.com"
            assert data["address"] == "123 Main St"

    @pytest.mark.asyncio
    async def test_supplier_rejects_unknown_field(self, mock_db, itam_app, patch_get_database_globally):
        _wire_crud_store(mock_db.suppliers)
        _authed_client_kwargs(itam_app, patch_get_database_globally)

        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/itam/catalog/suppliers", json={
                "name": "Bad Supplier",
                "loyaltyPoints": 500,
            })
            assert r.status_code == 422, r.text

    @pytest.mark.asyncio
    async def test_patch_category_updates_only_supplied_fields(self, mock_db, itam_app, patch_get_database_globally):
        _wire_crud_store(mock_db.asset_categories)
        _authed_client_kwargs(itam_app, patch_get_database_globally)

        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/itam/catalog/categories", json={"name": "Monitors", "notes": "original"})
            assert r.status_code == 201, r.text
            cid = r.json()["id"]
            created_updated_at = r.json()["updatedAt"]

            r2 = await ac.patch(f"/api/itam/catalog/categories/{cid}", json={"notes": "updated"})
            assert r2.status_code == 200, r2.text
            data = r2.json()
            assert data["name"] == "Monitors"  # untouched field survives the partial update
            assert data["notes"] == "updated"
            assert data["updatedAt"] >= created_updated_at

    @pytest.mark.asyncio
    async def test_delete_in_use_category_returns_409(self, mock_db, itam_app, patch_get_database_globally):
        _wire_crud_store(mock_db.asset_categories)
        mock_db.assets.count_documents = AsyncMock(return_value=1)
        _authed_client_kwargs(itam_app, patch_get_database_globally)

        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/itam/catalog/categories", json={"name": "In Use Category"})
            cid = r.json()["id"]

            r2 = await ac.delete(f"/api/itam/catalog/categories/{cid}")
            assert r2.status_code == 409, r2.text

            r3 = await ac.get(f"/api/itam/catalog/categories/{cid}")
            assert r3.status_code == 200, r3.text

    @pytest.mark.asyncio
    async def test_delete_unused_location_succeeds(self, mock_db, itam_app, patch_get_database_globally):
        _wire_crud_store(mock_db.locations)
        mock_db.assets.count_documents = AsyncMock(return_value=0)
        _authed_client_kwargs(itam_app, patch_get_database_globally)

        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/itam/catalog/locations", json={"name": "Unused Warehouse"})
            lid = r.json()["id"]

            r2 = await ac.delete(f"/api/itam/catalog/locations/{lid}")
            assert r2.status_code == 204, r2.text

    @pytest.mark.asyncio
    @pytest.mark.parametrize("kind", ["manufacturers", "categories", "locations", "suppliers"])
    async def test_every_registered_kind_is_tenant_scoped(self, kind, mock_db, itam_app, patch_get_database_globally):
        import itam_catalog_endpoints

        collection_name = itam_catalog_endpoints.CATALOG_KINDS[kind]
        raw_col = getattr(mock_db, collection_name)
        _wire_crud_store(raw_col)

        seen_filters = []
        original_find_one = raw_col.find_one

        async def _spy_find_one(f, *a, **kw):
            seen_filters.append(f)
            return await original_find_one(f, *a, **kw)

        raw_col.find_one = AsyncMock(side_effect=_spy_find_one)

        _authed_client_kwargs(itam_app, patch_get_database_globally)

        transport = ASGITransport(app=itam_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get(f"/api/itam/catalog/{kind}/some-nonexistent-id")
            assert r.status_code == 404

        assert len(seen_filters) >= 1
        assert all(f.get("tenantId") == "tenant-a" for f in seen_filters)
