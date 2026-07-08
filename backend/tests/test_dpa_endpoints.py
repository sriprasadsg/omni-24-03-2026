import pytest
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from auth_utils import get_current_user
import dpa_endpoints

# Inline helpers
def _db():
    db = AsyncMock()
    return db

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

# Tests
class TestDPACreate:
    @patch("dpa_endpoints._db")
    def test_create_starts_draft_unsigned(self, mock_db):
        db = AsyncMock()
        mock_db.return_value = db
        user = _user(role="admin")
        app = _app(dpa_endpoints.router, user)
        client = TestClient(app)

        payload = {"business_associate": "Test Vendor", "vendor_id": "vendor-1"}
        response = client.post("/api/dpa", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "draft"
        assert data["signed_by_us"] is False
        assert data["signed_by_vendor"] is False
        assert data["vendor_id"] == "vendor-1"
        db["dpa_agreements"].insert_one.assert_called_once()

    @patch("dpa_endpoints._db")
    def test_create_forbidden_for_non_admin(self, mock_db):
        user = _user(role="Viewer")
        app = _app(dpa_endpoints.router, user)
        client = TestClient(app)

        response = client.post("/api/dpa", json={"business_associate": "Test"})
        assert response.status_code == 403

class TestDPASign:
    @patch("dpa_endpoints._db")
    def test_single_party_sign_does_not_activate(self, mock_db):
        db = AsyncMock()
        mock_db.return_value = db
        # Setup: first party signed, second party False
        db["dpa_agreements"].find_one.return_value = {"id": "dpa-1", "signed_by_us": True, "signed_by_vendor": False}

        user = _user(role="admin")
        app = _app(dpa_endpoints.router, user)
        client = TestClient(app)

        response = client.post("/api/dpa/dpa-1/sign", json={"party": "us"})
        assert response.status_code == 200
        # Check that update_one for "active" status was NOT called
        for call in db["dpa_agreements"].update_one.call_args_list:
            assert "active" not in str(call)

    @patch("dpa_endpoints._db")
    def test_both_parties_signed_activates(self, mock_db):
        db = AsyncMock()
        mock_db.return_value = db
        # Setup: both parties True
        db["dpa_agreements"].find_one.return_value = {"id": "dpa-1", "signed_by_us": True, "signed_by_vendor": True}

        user = _user(role="admin")
        app = _app(dpa_endpoints.router, user)
        client = TestClient(app)

        response = client.post("/api/dpa/dpa-1/sign", json={"party": "vendor"})
        assert response.status_code == 200
        # Check that update_one for "active" status WAS called
        db["dpa_agreements"].update_one.assert_any_call({"id": "dpa-1"}, {"$set": {"status": "active"}})

class TestDPATerminate:
    @patch("dpa_endpoints._db")
    def test_terminate_sets_status(self, mock_db):
        db = AsyncMock()
        mock_db.return_value = db

        user = _user(role="admin")
        app = _app(dpa_endpoints.router, user)
        client = TestClient(app)

        response = client.post("/api/dpa/dpa-1/terminate", json={"reason": "test"})
        assert response.status_code == 200
        db["dpa_agreements"].update_one.assert_called_with(
            {"id": "dpa-1", "tenantId": "tenant-a"}, # tenant filter applied
            {"$set": {"status": "terminated", "termination_reason": "test", "terminated_by": "testuser", "terminated_at": pytest.any}}
        )

    @patch("dpa_endpoints._db")
    def test_terminate_respects_tenant_filter(self, mock_db):
        # Already checked in test_terminate_sets_status, but being explicit
        db = AsyncMock()
        mock_db.return_value = db
        user = _user(role="admin", tenant_id="tenant-b")
        app = _app(dpa_endpoints.router, user)
        client = TestClient(app)

        client.post("/api/dpa/dpa-1/terminate", json={"reason": "test"})
        # Assert filter uses tenant-b
        assert db["dpa_agreements"].update_one.call_args[0][0]["tenantId"] == "tenant-b"
