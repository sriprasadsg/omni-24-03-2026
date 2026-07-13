
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from auth_types import TokenData
from datetime import datetime
from authentication_service import get_current_user

# Mock the database for trust_service
class MockTrustService:
    def __init__(self):
        self.profile = MagicMock(
            company_name="TestCo",
            description="Test description",
            contact_email="test@test.com",
            logo_url="/logo.png",
            compliance_frameworks=["SOC2"],
            public_documents=[{"name": "Public Doc", "url": "/docs/public.pdf"}],
            private_documents=[{"name": "Private Doc", "url": "/docs/private.pdf"}]
        )
        self.requests = []

    def get_profile(self):
        return self.profile

    def update_profile(self, updates):
        for key, value in updates.items():
            setattr(self.profile, key, value)
        return self.profile

    def get_requests(self):
        return self.requests

    def create_request(self, request_data):
        mock_request = MagicMock(**request_data)
        mock_request.id = "new-req-id"
        mock_request.status = "Pending"
        mock_request.requested_at = datetime.now().isoformat()  # Ensure string
        mock_request.approved_at = None
        mock_request.approved_by = None
        self.requests.append(mock_request)
        return mock_request

    def update_request_status(self, request_id, status, approved_by=None):
        for req in self.requests:
            if req.id == request_id:
                req.status = status
                if status == 'Approved':
                    req.approved_at = datetime.now().isoformat()  # Ensure string
                    req.approved_by = approved_by
                else:
                    req.approved_at = None
                    req.approved_by = None
                return req
        return None

@pytest.fixture
def mock_trust_service():
    return MockTrustService()

@pytest.fixture
def client(mock_trust_service):
    from authentication_service import get_current_user
    from trust_endpoints import router

    app = FastAPI()
    app.include_router(router)

    # Mock authenticated user
    mock_user_admin = MagicMock(spec=TokenData)
    mock_user_admin.tenant_id = 'tenant-a'
    mock_user_admin.role = 'Super Admin'
    mock_user_admin.username = 'admin@tenant.com'

    # Mock non-admin user
    mock_user_non_admin = MagicMock(spec=TokenData)
    mock_user_non_admin.tenant_id = 'tenant-a'
    mock_user_non_admin.role = 'user'
    mock_user_non_admin.username = 'user@tenant.com'

    app.dependency_overrides[get_current_user] = lambda: mock_user_admin

    with patch('trust_endpoints.trust_service', mock_trust_service):
        yield TestClient(app)

class TestTrustCenterEndpoints:

    def test_get_profile(self, client):
        response = client.get("/api/trust-center/profile")
        assert response.status_code == 200
        assert response.json()["company_name"] == "TestCo"

    def test_update_profile_admin(self, client):
        response = client.put("/api/trust-center/profile", json={"company_name": "UpdatedCo"})
        assert response.status_code == 200
        assert response.json()["company_name"] == "UpdatedCo"

    def test_update_profile_non_admin(self, client):
        # Temporarily override dependency to be a non-admin user
        from authentication_service import get_current_user
        mock_user_non_admin = MagicMock(spec=TokenData)
        mock_user_non_admin.tenant_id = 'tenant-a'
        mock_user_non_admin.role = 'user'
        mock_user_non_admin.username = 'user@tenant.com'
        client.app.dependency_overrides[get_current_user] = lambda: mock_user_non_admin

        response = client.put("/api/trust-center/profile", json={"company_name": "UnauthorizedCo"})
        assert response.status_code == 403
        assert "Admin access required" in response.json()["detail"]

    def test_get_requests_admin(self, client):
        response = client.get("/api/trust-center/requests")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_get_requests_non_admin(self, client):
        from authentication_service import get_current_user
        mock_user_non_admin = MagicMock(spec=TokenData)
        mock_user_non_admin.tenant_id = 'tenant-a'
        mock_user_non_admin.role = 'user'
        mock_user_non_admin.username = 'user@tenant.com'
        client.app.dependency_overrides[get_current_user] = lambda: mock_user_non_admin

        response = client.get("/api/trust-center/requests")
        assert response.status_code == 403
        assert "Admin access required" in response.json()["detail"]

    def test_create_request(self, client, mock_trust_service):
        request_data = {
            "requester_email": "req@example.com",
            "company": "ReqCo",
            "reason": "Test reason"
        }
        response = client.post("/api/trust-center/requests", json=request_data)
        assert response.status_code == 200
        assert response.json()["requester_email"] == "req@example.com"
        assert mock_trust_service.requests[0].company == "ReqCo"

    def test_update_request_status_admin(self, client, mock_trust_service):
        # Create a request first
        client.post("/api/trust-center/requests", json={
            "requester_email": "req2@example.com",
            "company": "ReqCo2",
            "reason": "Test reason 2"
        })
        request_id = mock_trust_service.requests[0].id

        update_data = {"status": "Approved", "approved_by": "admin@tenant.com"}
        response = client.put(f"/api/trust-center/requests/{request_id}", json=update_data)
        assert response.status_code == 200
        assert response.json()["status"] == "Approved"
        assert response.json()["approved_by"] == "admin@tenant.com"

    def test_update_request_status_non_admin(self, client):
        from authentication_service import get_current_user
        mock_user_non_admin = MagicMock(spec=TokenData)
        mock_user_non_admin.tenant_id = 'tenant-a'
        mock_user_non_admin.role = 'user'
        mock_user_non_admin.username = 'user@tenant.com'
        client.app.dependency_overrides[get_current_user] = lambda: mock_user_non_admin

        response = client.put("/api/trust-center/requests/some-id", json={"status": "Approved"})
        assert response.status_code == 403
        assert "Admin access required" in response.json()["detail"]

    def test_update_request_status_not_found(self, client):
        update_data = {"status": "Approved", "approved_by": "admin@tenant.com"}
        response = client.put("/api/trust-center/requests/nonexistent-id", json=update_data)
        assert response.status_code == 404
        assert "Request not found" in response.json()["detail"]
