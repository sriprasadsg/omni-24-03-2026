import pytest
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from auth_utils import get_current_user
import vendor_endpoints

def _user(role="admin", tenant_id="tenant-a"):
    user = AsyncMock()
    user.role = role
    user.tenant_id = tenant_id
    user.username = "testuser"
    return user

def _app(router, user):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    return app

class TestAddSubprocessor:
    @patch("vendor_service.vendor_service.add_subprocessor", new_callable=AsyncMock)
    def test_add_subprocessor_success(self, mock_add):
        mock_add.return_value = {"id": "sub-1", "name": "Test Sub"}
        user = _user(role="admin")
        app = _app(vendor_endpoints.router, user)
        client = TestClient(app)

        response = client.post("/api/vendors/vendor-1/subprocessors", json={"name": "Test Sub"})
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Sub"
        mock_add.assert_called_once()

class TestRemoveSubprocessor:
    @patch("vendor_service.vendor_service.remove_subprocessor", new_callable=AsyncMock)
    def test_remove_subprocessor_success(self, mock_rm):
        mock_rm.return_value = True
        user = _user(role="admin")
        app = _app(vendor_endpoints.router, user)
        client = TestClient(app)

        response = client.delete("/api/vendors/vendor-1/subprocessors/sub-1")
        assert response.status_code == 200
        mock_rm.assert_called_once()

class TestSubprocessorRBAC:
    @patch("vendor_service.vendor_service.add_subprocessor", new_callable=AsyncMock)
    def test_add_subprocessor_forbidden(self, mock_add):
        user = _user(role="Viewer")
        app = _app(vendor_endpoints.router, user)
        client = TestClient(app)

        response = client.post("/api/vendors/vendor-1/subprocessors", json={"name": "Test"})
        assert response.status_code == 403