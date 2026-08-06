"""ITAM License tests — Phase 60 Plan 01, Task 1: license management end-to-end.
"""
import sys
import os
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone, timedelta

import pytest
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.conftest import make_test_app, make_token_data
from authentication_service import get_current_user as real_get_current_user
from itam_license_endpoints import router # Import the router to build the app


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


@pytest.fixture
def mock_db():
    db = MagicMock()
    for name in (
        "licenses", "license_assignments", "users", "assets", "manufacturers", "assignment_history"
    ):
        col = MagicMock()
        col.find_one = AsyncMock(return_value=None)
        col.insert_one = AsyncMock()
        col.count_documents = AsyncMock(return_value=0) # Default no assignments
        col.find_one_and_update = AsyncMock(return_value=None)
        col.delete_one = AsyncMock()

        # Chainable cursor for find
        _cursor = MagicMock()
        _cursor.limit.return_value = _cursor
        _cursor.to_list = AsyncMock(return_value=[])
        col.find.return_value = _cursor

        setattr(db, name, col)

    # Specific mock for assignment history in itam_license_service
    _history_cursor = MagicMock()
    _history_cursor.sort.return_value = _history_cursor
    _history_cursor.limit.return_value = _history_cursor
    _history_cursor.to_list = AsyncMock(return_value=[])
    db.assignment_history.find = MagicMock(return_value=_history_cursor)

    return db


@pytest.fixture(autouse=True)
def patch_get_database_globally(mock_db, monkeypatch):
    import itam_license_endpoints
    import itam_license_service
    import itam_asset_endpoints # For _require_itam_admin

    _current_tenant_id = "tenant-a"

    def get_mock_tenant_db():
        return MockTenantIsolatedDatabase(mock_db, _current_tenant_id)

    def _patch_all():
        monkeypatch.setattr(itam_license_endpoints, "get_database", get_mock_tenant_db)

    _patch_all()

    def set_current_tenant_id(tenant_id):
        nonlocal _current_tenant_id
        _current_tenant_id = tenant_id
        _patch_all()

    return set_current_tenant_id


@pytest.fixture
def license_app(mock_db, patch_get_database_globally, monkeypatch):
    import itam_asset_endpoints # For _require_itam_admin
    # Patch RBAC dependency
    monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=True))

    app, _ = make_test_app(router)
    return app


# Helper function for ISO date strings
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

def _future_iso(days: int = 30) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class TestLicenseManagement:

    @pytest.mark.asyncio
    async def test_create_license(self, mock_db, license_app, patch_get_database_globally):
        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        patch_get_database_globally("tenant-a")
        license_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=license_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            payload = {
                "name": "Windows 11 Pro",
                "seatCount": 5,
                "expiryDate": _future_iso(),
                "isReassignable": True
            }
            r = await ac.post("/api/itam/licenses", json=payload)

        assert r.status_code == 201, r.text
        data = r.json()
        assert "id" in data
        assert data["name"] == "Windows 11 Pro"
        assert data["seatCount"] == 5
        assert data["tenantId"] == "tenant-a"
        mock_db.licenses.insert_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_licenses(self, mock_db, license_app, patch_get_database_globally):
        mock_db.licenses.find.return_value.to_list.return_value = [
            {"id": "lic-1", "name": "Windows 10", "seatCount": 10, "tenantId": "tenant-a"},
            {"id": "lic-2", "name": "Office 365", "seatCount": 20, "tenantId": "tenant-a"},
        ]
        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        patch_get_database_globally("tenant-a")
        license_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=license_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/itam/licenses")

        assert r.status_code == 200, r.text
        data = r.json()
        assert len(data) == 2
        assert data[0]["name"] == "Windows 10"
        assert data[1]["name"] == "Office 365"

    @pytest.mark.asyncio
    async def test_get_license(self, mock_db, license_app, patch_get_database_globally):
        mock_db.licenses.find_one.return_value = {"id": "lic-1", "name": "Windows 10", "seatCount": 10, "tenantId": "tenant-a"}
        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        patch_get_database_globally("tenant-a")
        license_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=license_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/itam/licenses/lic-1")

        assert r.status_code == 200, r.text
        data = r.json()
        assert data["id"] == "lic-1"
        assert data["name"] == "Windows 10"

    @pytest.mark.asyncio
    async def test_update_license(self, mock_db, license_app, patch_get_database_globally):
        original_doc = {"id": "lic-1", "name": "Windows 10", "seatCount": 10, "tenantId": "tenant-a", "createdAt": _now_iso()}
        updated_doc = {**original_doc, "name": "Windows 11", "seatCount": 15}
        mock_db.licenses.find_one_and_update.return_value = updated_doc
        current_user = make_token_data(tenant_id="tenant-a", role="admin")
        patch_get_database_globally("tenant-a")
        license_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=license_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            payload = {"name": "Windows 11", "seatCount": 15}
            r = await ac.patch("/api/itam/licenses/lic-1", json=payload)

        assert r.status_code == 200, r.text
        data = r.json()
        assert data["name"] == "Windows 11"
        assert data["seatCount"] == 15
        mock_db.licenses.find_one_and_update.assert_called_once()
        args, kwargs = mock_db.licenses.find_one_and_update.call_args
        assert args[0]["id"] == "lic-1"
        assert args[1]["$set"]["name"] == "Windows 11"
        assert args[1]["$set"]["seatCount"] == 15
        assert "updatedAt" in args[1]["$set"]


class TestLicenseAssignment:

    @pytest.mark.asyncio
    async def test_assign_license_seat_to_user(self, mock_db, license_app, patch_get_database_globally):
        mock_db.licenses.find_one.return_value = {"id": "lic-1", "name": "Windows 11", "seatCount": 5, "tenantId": "tenant-a"}
        mock_db.users.find_one.return_value = {"id": "user-7"}
        mock_db.license_assignments.count_documents.return_value = 0 # No seats assigned yet
        mock_db.license_assignments.insert_one.return_value = MagicMock(inserted_id="la-abc")
        mock_db.assignment_history.insert_one.return_value = MagicMock(inserted_id="ah-xyz")

        current_user = make_token_data(tenant_id="tenant-a", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        license_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=license_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            payload = {"targetType": "user", "targetId": "user-7", "note": "Assigned to HR"}
            r = await ac.post("/api/itam/licenses/lic-1/assign", json=payload)

        assert r.status_code == 201, r.text
        data = r.json()
        assert "id" in data
        assert data["licenseId"] == "lic-1"
        assert data["targetType"] == "user"
        assert data["targetId"] == "user-7"
        mock_db.license_assignments.insert_one.assert_called_once()
        mock_db.assignment_history.insert_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_assign_license_seat_to_asset(self, mock_db, license_app, patch_get_database_globally):
        mock_db.licenses.find_one.return_value = {"id": "lic-1", "name": "Windows 11", "seatCount": 5, "tenantId": "tenant-a"}
        mock_db.assets.find_one.return_value = {"id": "asset-abc"}
        mock_db.license_assignments.count_documents.return_value = 0
        mock_db.license_assignments.insert_one.return_value = MagicMock(inserted_id="la-abc")
        mock_db.assignment_history.insert_one.return_value = MagicMock(inserted_id="ah-xyz")

        current_user = make_token_data(tenant_id="tenant-a", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        license_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=license_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            payload = {"targetType": "asset", "targetId": "asset-abc", "note": "Installed on server"}
            r = await ac.post("/api/itam/licenses/lic-1/assign", json=payload)

        assert r.status_code == 201, r.text
        data = r.json()
        assert data["targetType"] == "asset"
        assert data["targetId"] == "asset-abc"

    @pytest.mark.asyncio
    async def test_assign_license_seat_no_seats_available(self, mock_db, license_app, patch_get_database_globally):
        mock_db.licenses.find_one.return_value = {"id": "lic-1", "name": "Windows 11", "seatCount": 1, "tenantId": "tenant-a"}
        mock_db.users.find_one.return_value = {"id": "user-7"}
        mock_db.license_assignments.count_documents.return_value = 1 # One seat already assigned

        current_user = make_token_data(tenant_id="tenant-a", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        license_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=license_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            payload = {"targetType": "user", "targetId": "user-8"}
            r = await ac.post("/api/itam/licenses/lic-1/assign", json=payload)

        assert r.status_code == 400, r.text
        assert "No seats available" in r.json()["detail"]
        mock_db.license_assignments.insert_one.assert_not_called()
        mock_db.assignment_history.insert_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_reclaim_license_seat(self, mock_db, license_app, patch_get_database_globally):
        assignment_doc = {
            "id": "la-123",
            "licenseId": "lic-1",
            "targetType": "user",
            "targetId": "user-7",
            "tenantId": "tenant-a",
            "assignedBy": "testuser",
            "assignedAt": _now_iso(),
        }
        mock_db.license_assignments.find_one.return_value = assignment_doc
        mock_db.license_assignments.delete_one.return_value = MagicMock(deleted_count=1)
        mock_db.assignment_history.insert_one.return_value = MagicMock(inserted_id="ah-xyz")

        current_user = make_token_data(tenant_id="tenant-a", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        license_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=license_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.delete("/api/itam/licenses/assignments/la-123?note=User%20left")

        assert r.status_code == 204
        mock_db.license_assignments.delete_one.assert_called_once_with({"id": "la-123", "tenantId": "tenant-a"})
        mock_db.assignment_history.insert_one.assert_called_once()
        args, kwargs = mock_db.assignment_history.insert_one.call_args
        assert args[0]["action"] == "license_reclaim"
        assert args[0]["targetId"] == "user-7"

    @pytest.mark.asyncio
    async def test_list_license_assignments(self, mock_db, license_app, patch_get_database_globally):
        mock_db.licenses.find_one.return_value = {"id": "lic-1", "name": "Windows 11", "seatCount": 5, "tenantId": "tenant-a"}
        mock_db.license_assignments.find.return_value.to_list.return_value = [
            {"id": "la-1", "licenseId": "lic-1", "targetType": "user", "targetId": "user-a"},
            {"id": "la-2", "licenseId": "lic-1", "targetType": "asset", "targetId": "asset-b"},
        ]
        current_user = make_token_data(tenant_id="tenant-a", username="admin@example.com")
        patch_get_database_globally("tenant-a")
        license_app.dependency_overrides[real_get_current_user] = lambda: current_user

        transport = ASGITransport(app=license_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/itam/licenses/lic-1/assignments")

        assert r.status_code == 200, r.text
        data = r.json()
        assert len(data) == 2
        assert data[0]["id"] == "la-1"
        assert data[1]["id"] == "la-2"
