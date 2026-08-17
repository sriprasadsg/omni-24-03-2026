"""ITAM Component tests — Phase 60 Plan 01, Task 3: component management end-to-end.
"""
import sys
import os
import bson
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone
from bson import ObjectId as BsonObjectId # Import ObjectId from bson directly for use in test mocks

import pytest
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../backend"))

from tests.conftest import make_test_app, make_token_data
from authentication_service import get_current_user as real_get_current_user
from backend.itam_component_endpoints import router, asset_components_router # Import the routers to build the app
from backend.itam_component_service import ComponentNotFoundError, AssetNotFoundError, ComponentService # Import ComponentService here


# Mock database and app fixtures (similar to itam_lifecycle_test_support)
class MockTenantIsolatedCollection:
    def __init__(self, collection_name, tenant_id, raw_collection_mock):
        self._collection_name = collection_name
        self._tenant_id = tenant_id
        self._raw_collection = raw_collection_mock

        # Asynchronous methods that directly interact with the raw mock collection
        async def _find_one(f, *args, **kwargs):
            return await raw_collection_mock.find_one({**(f or {}), "tenantId": self._tenant_id}, *args, **kwargs)

        async def _insert_one(doc, *args, **kwargs):
            return await raw_collection_mock.insert_one({**doc, "tenantId": self._tenant_id}, *args, **kwargs)

        async def _count_documents(f, *args, **kwargs):
            return await raw_collection_mock.count_documents({**(f or {}), "tenantId": self._tenant_id}, *args, **kwargs)

        async def _find_one_and_update(f, u, *args, **kwargs):
            return await raw_collection_mock.find_one_and_update({**(f or {}), "tenantId": self._tenant_id}, u, *args, **kwargs)

        async def _delete_one(f, *args, **kwargs):
            return await raw_collection_mock.delete_one({**(f or {}), "tenantId": self._tenant_id}, *args, **kwargs)

        async def _update_one(f, u, *args, **kwargs):
            return await raw_collection_mock.update_one({**(f or {}), "tenantId": self._tenant_id}, u, *args, **kwargs)

        async def _update_many(f, u, *args, **kwargs):
            return await raw_collection_mock.update_many({**(f or {}), "tenantId": self._tenant_id}, u, *args, **kwargs)

        async def _find_one_and_delete(f, *args, **kwargs):
            return await raw_collection_mock.find_one_and_delete({**(f or {}), "tenantId": self._tenant_id}, *args, **kwargs)


        self.find_one = _find_one
        self.insert_one = _insert_one
        self.count_documents = _count_documents
        self.find_one_and_update = _find_one_and_update
        self.delete_one = _delete_one
        self.update_one = _update_one
        self.update_many = _update_many
        self.find_one_and_delete = _find_one_and_delete

        # find must return a cursor-like object with skip, limit, to_list
        def _find(f=None, *args, **kwargs):
            raw_filter = {**(f or {}), "tenantId": self._tenant_id}
            cursor = raw_collection_mock.find(raw_filter, *args, **kwargs)
            return cursor

        self.find = _find


class MockTenantIsolatedDatabase:
    def __init__(self, raw_db_mock, tenant_id):
        self._raw_db = raw_db_mock
        self._tenant_id = tenant_id

    def __getattr__(self, name):
        return MockTenantIsolatedCollection(name, self._tenant_id, getattr(self._raw_db, name))

    def __getitem__(self, name):
        return self.__getattr__(name)


@pytest.fixture
def mock_db():
    db = MagicMock()
    for name in (
        "components", "assets"
    ):
        col = MagicMock()
        col.find_one = AsyncMock(return_value={"_id": "mock_id", "name": "Mock Item", "tenantId": "tenant-a"})
        col.insert_one = AsyncMock(return_value=MagicMock(inserted_id=BsonObjectId()))
        col.count_documents = AsyncMock(return_value=0)
        col.find_one_and_update = AsyncMock(return_value=None)
        col.delete_one = AsyncMock()
        col.update_one = AsyncMock() # Add update_one mock
        col.update_many = AsyncMock() # Add update_many mock
        col.find_one_and_delete = AsyncMock() # Add find_one_and_delete mock

        _cursor = MagicMock()
        _cursor.limit.return_value = _cursor
        _cursor.skip.return_value = _cursor # Add skip mock
        _cursor.to_list = AsyncMock(return_value=[])
        col.find.return_value = _cursor

        setattr(db, name, col)

    return db


@pytest.fixture(autouse=True)
def patch_get_database_globally(mock_db, monkeypatch):
    import itam_component_endpoints
    import itam_component_service

    _current_tenant_id = "tenant-a"

    def get_mock_tenant_db():
        return MockTenantIsolatedDatabase(mock_db, _current_tenant_id)

    def _patch_all():
        monkeypatch.setattr(bson, "ObjectId", MagicMock(side_effect=lambda: BsonObjectId("654c60037a5f67a213a4a034")))
        monkeypatch.setattr(itam_component_service, "get_database", get_mock_tenant_db)
        monkeypatch.setattr(
            itam_component_endpoints,
            "get_component_service",
            lambda: ComponentService()
        )


    _patch_all()

    def set_current_tenant_id(tenant_id):
        nonlocal _current_tenant_id
        _current_tenant_id = tenant_id
        _patch_all()

    return set_current_tenant_id


@pytest.fixture
def component_app(mock_db, patch_get_database_globally, monkeypatch):
    import itam_asset_endpoints
    monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=True))

    app, _ = make_test_app(router, asset_components_router)
    return app


# Helper function for ISO date strings
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class TestComponentManagement:

    @pytest.mark.asyncio
    async def test_create_component(self, mock_db, component_app, patch_get_database_globally):
        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        patch_get_database_globally("tenant-a")
        component_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=component_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            payload = {
                "name": "NVIDIA RTX 3080",
                "type": "GPU",
            }
            r = await ac.post("/api/itam/components", json=payload)

        assert r.status_code == 201, r.text
        data = r.json()
        assert "id" in data or "_id" in data
        assert data["name"] == "NVIDIA RTX 3080"
        assert data["type"] == "GPU"
        assert data["tenantId"] == "tenant-a"
        mock_db.components.insert_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_components(self, mock_db, component_app, patch_get_database_globally):
        mock_db.components.find.return_value.to_list.return_value = [
            {"id": "comp-1", "name": "CPU i7", "type": "CPU", "tenantId": "tenant-a"},
            {"id": "comp-2", "name": "RAM 16GB", "type": "RAM", "tenantId": "tenant-a"},
        ]
        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        patch_get_database_globally("tenant-a")
        component_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=component_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/itam/components")

        assert r.status_code == 200, r.text
        data = r.json()
        assert len(data) == 2
        assert data[0]["name"] == "CPU i7"
        assert data[1]["name"] == "RAM 16GB"

    @pytest.mark.asyncio
    async def test_attach_component_to_asset_success(self, mock_db, component_app, patch_get_database_globally):
        mock_db.components.find_one.return_value = {
            "_id": "comp-1", "name": "CPU i7", "type": "CPU", "tenantId": "tenant-a", "createdAt": _now_iso()
        }
        mock_db.assets.find_one.return_value = {
            "id": "asset-123", "name": "Workstation", "tenantId": "tenant-a", "components": []
        }
        mock_db.assets.update_one.return_value = MagicMock(matched_count=1) # Changed from find_one_and_update
        mock_db.components.find_one_and_update.return_value = {
            "_id": "comp-1", "name": "CPU i7", "parentAssetId": "asset-123", "tenantId": "tenant-a"
        }

        current_user = make_token_data(tenant_id="tenant-a", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        component_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=component_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/itam/components/comp-1/attach/asset-123")

        assert r.status_code == 200, r.text
        data = r.json()
        print(f"DEBUG: {data}")
        component_id_returned = data.get("id") or data.get("_id")
        assert component_id_returned is not None
        assert data["parentAssetId"] == "asset-123"
        mock_db.components.find_one.assert_called_once()
        mock_db.assets.find_one.assert_called_once()
        mock_db.assets.update_one.assert_called_once() # Changed assertion
        mock_db.components.find_one_and_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_attach_component_not_found(self, mock_db, component_app, patch_get_database_globally):
        mock_db.components.find_one.return_value = None

        current_user = make_token_data(tenant_id="tenant-a", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        component_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=component_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/itam/components/comp-999/attach/asset-123")

        assert r.status_code == 404, r.text
        assert "Component not found" in r.json()["detail"]
        mock_db.assets.find_one.assert_not_called()
        mock_db.assets.update_one.assert_not_called() # Changed from find_one_and_update

    @pytest.mark.asyncio
    async def test_attach_asset_not_found(self, mock_db, component_app, patch_get_database_globally):
        mock_db.components.find_one.return_value = {
            "_id": "comp-1", "name": "CPU i7", "type": "CPU", "tenantId": "tenant-a", "createdAt": _now_iso()
        }
        mock_db.assets.find_one.return_value = None

        current_user = make_token_data(tenant_id="tenant-a", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        component_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=component_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/itam/components/comp-1/attach/asset-999")

        assert r.status_code == 404, r.text
        assert "Asset not found" in r.json()["detail"]
        mock_db.assets.update_one.assert_not_called() # Changed from find_one_and_update

    @pytest.mark.asyncio
    async def test_detach_component_from_asset_success(self, mock_db, component_app, patch_get_database_globally):
        mock_db.components.find_one.return_value = {
            "_id": "comp-1", "parentAssetId": "asset-123", "tenantId": "tenant-a"
        }
        mock_db.assets.find_one.return_value = {
            "id": "asset-123", "name": "Workstation", "tenantId": "tenant-a", "components": ["comp-1"]
        }
        mock_db.assets.update_one.return_value = MagicMock(matched_count=1) # Changed from find_one_and_update
        mock_db.components.find_one_and_update.return_value = {
            "_id": "comp-1", "name": "CPU i7", "tenantId": "tenant-a"
        }

        current_user = make_token_data(tenant_id="tenant-a", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        component_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=component_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/itam/components/comp-1/detach/asset-123")

        assert r.status_code == 200, r.text
        data = r.json()
        print(f"DEBUG DETACH: {data}")
        component_id_returned = data.get("id") or data.get("_id")
        assert component_id_returned is not None
        assert data.get("parentAssetId") is None
        mock_db.components.find_one.assert_called_once()
        mock_db.assets.update_one.assert_called_once() # Changed assertion
        mock_db.components.find_one_and_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_detach_component_not_attached(self, mock_db, component_app, patch_get_database_globally):
        mock_db.components.find_one.return_value = {
            "id": "comp-1", "tenantId": "tenant-a" # No parentAssetId
        }
        mock_db.assets.find_one.return_value = {
            "id": "asset-123", "name": "Workstation", "tenantId": "tenant-a", "components": []
        }

        current_user = make_token_data(tenant_id="tenant-a", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        component_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=component_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/itam/components/comp-1/detach/asset-123")

        assert r.status_code == 400, r.text
        assert "Component comp-1 is not attached to asset asset-123" in r.json()["detail"]
        mock_db.assets.update_one.assert_not_called() # Changed from find_one_and_update
        mock_db.components.find_one_and_update.assert_not_called()


class TestAssetComponentsSubResource:
    """ROADMAP Phase 60 success criterion 3: a component attached to a parent
    asset must be visible, hydrated, as a listing on that asset's record —
    not just a bare id riding along on the generic asset GET response."""

    @pytest.mark.asyncio
    async def test_list_asset_components(self, mock_db, component_app, patch_get_database_globally):
        mock_db.assets.find_one.return_value = {"id": "asset-123", "tenantId": "tenant-a"}
        mock_db.components.find.return_value.to_list.return_value = [
            {"id": "comp-1", "name": "RAM 16GB", "type": "ram", "parentAssetId": "asset-123", "tenantId": "tenant-a"},
            {"id": "comp-2", "name": "SSD 1TB", "type": "storage", "parentAssetId": "asset-123", "tenantId": "tenant-a"},
        ]
        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        patch_get_database_globally("tenant-a")
        component_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=component_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/assets/asset-123/components")

        assert r.status_code == 200, r.text
        data = r.json()
        assert len(data) == 2
        assert data[0]["name"] == "RAM 16GB"
        assert data[1]["name"] == "SSD 1TB"

    @pytest.mark.asyncio
    async def test_list_asset_components_asset_not_found(self, mock_db, component_app, patch_get_database_globally):
        mock_db.assets.find_one.return_value = None
        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        patch_get_database_globally("tenant-a")
        component_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=component_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/assets/asset-999/components")

        assert r.status_code == 404, r.text


class TestComponentRbac:
    """ITAM-LIC-03, D-05: non-admin gets 403 on both router objects."""

    @pytest.mark.asyncio
    async def test_rbac_denied_create_returns_403(self, mock_db, component_app, monkeypatch):
        import itam_asset_endpoints
        monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=False))
        current_user = make_token_data(tenant_id="tenant-a", role="user", username="user@example.com")
        component_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=component_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/itam/components", json={"name": "8GB DIMM", "type": "RAM"})

        assert r.status_code == 403, r.text

    @pytest.mark.asyncio
    async def test_rbac_denied_list_asset_components_returns_403(self, mock_db, component_app, monkeypatch):
        import itam_asset_endpoints
        monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=False))
        current_user = make_token_data(tenant_id="tenant-a", role="user", username="user@example.com")
        component_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=component_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/assets/asset-1/components")

        assert r.status_code == 403, r.text