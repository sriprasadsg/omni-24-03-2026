"""ITAM Consumable tests — Phase 60 Plan 01, Task 2: consumable management end-to-end.
"""
import sys
import os
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.conftest import make_test_app, make_token_data
from authentication_service import get_current_user as real_get_current_user
from backend.itam_consumable_endpoints import router
from backend.itam_consumable_service import ConsumableNotFoundError, ConsumableService
from backend.itam_asset_endpoints import verify_permission as itam_asset_verify_permission

# Mock database and app fixtures (similar to itam_lifecycle_test_support)
class MockTenantIsolatedCollection:
    def __init__(self, collection_name, tenant_id, raw_collection_mock):
        self._collection_name = collection_name
        self._tenant_id = tenant_id
        self._raw_collection = raw_collection_mock

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

        def _find(f=None, *args, **kwargs):
            raw_filter = {**(f or {}), "tenantId": self._tenant_id}
            return raw_collection_mock.find(raw_filter, *args, **kwargs)

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
        "itam_consumables", "itam_consumable_checkouts"
    ):
        col = MagicMock()
        col.find_one = AsyncMock(return_value={"_id": "con-123", "name": "HDMI Cable", "initialQuantity": 100, "unitType": "unit", "availableQuantity": 100, "tenantId": "tenant-a", "checkoutRecords": [], "notes": None, "description": None, "createdAt": "2024-01-01T00:00:00Z", "updatedAt": "2024-01-01T00:00:00Z"})
        col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock_inserted_id")) 
        col.count_documents = AsyncMock(return_value=0)
        col.find_one_and_update = AsyncMock(return_value={"_id": "mock_id", "name": "Mock Item", "availableQuantity": 99, "tenantId": "tenant-a"}) 
        col.delete_one = AsyncMock()
        col.update_one = AsyncMock()
        col.update_many = AsyncMock()
        col.find_one_and_delete = AsyncMock()

        _cursor = MagicMock()
        _cursor.limit.return_value = _cursor
        _cursor.skip.return_value = _cursor
        _cursor.to_list = AsyncMock(return_value=[
            {"id": "con-1", "name": "Pen", "initialQuantity": 50, "unitType": "unit", "availableQuantity": 50, "tenantId": "tenant-a"},
            {"id": "con-2", "name": "Paper", "initialQuantity": 200, "unitType": "unit", "availableQuantity": 200, "tenantId": "tenant-a"},
        ])
        col.find.return_value = _cursor

        setattr(db, name, col)

    return db


@pytest.fixture(autouse=True)
def patch_get_database_globally(mock_db, monkeypatch):
    # itam_consumable_endpoints.py imports itam_consumable_service via a bare
    # (non-`backend.`-prefixed) import — see router_registry.py's cwd=backend/
    # launcher contract — so router.Depends(get_consumable_service) is bound
    # at decoration time to the *bare* module's function object. Patching the
    # `backend.`-dotted module (a separate sys.modules entry for the same
    # file) would silently no-op against the real get_database().
    import itam_consumable_endpoints
    import itam_consumable_service
    import authentication_service

    _current_tenant_id = "tenant-a"

    def get_mock_tenant_db():
        return MockTenantIsolatedDatabase(mock_db, _current_tenant_id)

    def _patch_all():
        monkeypatch.setattr(itam_consumable_service, "get_database", get_mock_tenant_db)
        monkeypatch.setattr(itam_consumable_endpoints, "get_consumable_service", lambda: itam_consumable_service.ConsumableService())

    _patch_all()

    def set_current_tenant_id(tenant_id):
        nonlocal _current_tenant_id
        _current_tenant_id = tenant_id
        _patch_all()

    return set_current_tenant_id


@pytest.fixture
def consumable_app(mock_db, patch_get_database_globally, monkeypatch):
    import backend.itam_asset_endpoints as itam_asset_endpoints
    monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=True))

    app, _ = make_test_app(router)
    return app


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class TestConsumableManagement:

    @pytest.mark.asyncio
    async def test_create_consumable(self, mock_db, consumable_app):
        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        consumable_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=consumable_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            payload = {
                "name": "HDMI Cable",
                "initialQuantity": 100,
                "unitType": "unit",
            }
            r = await ac.post("/api/itam/consumables", json=payload)

        assert r.status_code == 201, r.text
        data = r.json()
        assert "id" in data
        assert data["name"] == "HDMI Cable"
        assert data["availableQuantity"] == 100
        assert data["tenantId"] == "tenant-a"
        mock_db.itam_consumables.insert_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_consumables(self, mock_db, consumable_app):
        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        consumable_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=consumable_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/itam/consumables")

        assert r.status_code == 200, r.text
        data = r.json()
        assert len(data) == 2
        assert data[0]["name"] == "Pen"
        assert data[1]["name"] == "Paper"
