import pytest
from unittest.mock import AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from auth_utils import get_current_user
import dpa_endpoints

def _user(role="admin", tenant_id="tenant-a"):
    user = AsyncMock()
    user.role = role
    user.tenant_id = tenant_id
    user.username = "testuser"
    return user

def _app(router, user, db):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    # Override the _db dependency with a lambda returning the mock db
    app.dependency_overrides[dpa_endpoints._db] = lambda: db
    return app

class TestDPACreate:
    def test_create_starts_draft_unsigned(self):
        db = {"dpa_agreements": AsyncMock()}
        db["dpa_agreements"].insert_one = AsyncMock()

        user = _user(role="admin")
        app = _app(dpa_endpoints.router, user, db)
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

    def test_create_forbidden_for_non_admin(self):
        db = {"dpa_agreements": AsyncMock()}
        user = _user(role="Viewer")
        app = _app(dpa_endpoints.router, user, db)
        client = TestClient(app)

        response = client.post("/api/dpa", json={"business_associate": "Test"})
        assert response.status_code == 403

class TestDPASign:
    def test_single_party_sign_does_not_activate(self):
        db = {"dpa_agreements": AsyncMock()}
        db["dpa_agreements"].find_one.return_value = {"id": "dpa-1", "signed_by_us": True, "signed_by_vendor": False}

        user = _user(role="admin")
        app = _app(dpa_endpoints.router, user, db)
        client = TestClient(app)

        response = client.post("/api/dpa/dpa-1/sign", json={"party": "us"})
        assert response.status_code == 200
        for call in db["dpa_agreements"].update_one.call_args_list:
            args = call[0]
            assert "active" not in str(args)

    def test_both_parties_signed_activates(self):
        db = {"dpa_agreements": AsyncMock()}
        db["dpa_agreements"].find_one.return_value = {"id": "dpa-1", "signed_by_us": True, "signed_by_vendor": True}

        user = _user(role="admin")
        app = _app(dpa_endpoints.router, user, db)
        client = TestClient(app)

        response = client.post("/api/dpa/dpa-1/sign", json={"party": "vendor"})
        assert response.status_code == 200
        db["dpa_agreements"].update_one.assert_any_call(
            {"id": "dpa-1", "tenantId": "tenant-a"},
            {"$set": {"status": "active"}}
        )

class TestDPATerminate:
    def test_terminate_sets_status(self):
        db = {"dpa_agreements": AsyncMock()}

        user = _user(role="admin")
        app = _app(dpa_endpoints.router, user, db)
        client = TestClient(app)

        response = client.post("/api/dpa/dpa-1/terminate", json={"reason": "test"})
        assert response.status_code == 200
        db["dpa_agreements"].update_one.assert_called()
        call_args = db["dpa_agreements"].update_one.call_args
        filter_, update = call_args[0]
        assert filter_.get("id") == "dpa-1"
        assert update["$set"]["status"] == "terminated"

    def test_terminate_respects_tenant_filter(self):
        db = {"dpa_agreements": AsyncMock()}
        user = _user(role="admin", tenant_id="tenant-b")
        app = _app(dpa_endpoints.router, user, db)
        client = TestClient(app)

        client.post("/api/dpa/dpa-1/terminate", json={"reason": "test"})
        call_args = db["dpa_agreements"].update_one.call_args
        filter_, _ = call_args[0]
        assert filter_.get("tenantId") == "tenant-b"