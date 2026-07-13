"""Integration tests for ReBAC (OpenFGA) authorization."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

# Mock the ReBAC service before importing the app
mock_rebac = AsyncMock()
mock_rebac.check_permission = AsyncMock(return_value=True)

with patch("rebac_service.get_reback_service", return_value=mock_rebac):
    from backend.app import app

client = TestClient(app)


def test_rebac_allow_add_control():
    """Test that ReBAC allows adding a control when permission exists."""
    # Mock user with permission
    with patch("authentication_service.get_current_user", return_value=type("User", (), {"username": "testuser", "role": "admin", "tenant_id": "tenant1"})()):
        mock_rebac.check_permission.return_value = True
        response = client.post(
            "/api/compliance/test-framework/controls",
            json={"id": "CTRL-1", "name": "Test Control"},
        )
        assert response.status_code == 200
        assert response.json()["id"] == "CTRL-1"


def test_rebac_deny_add_control():
    """Test that ReBAC denies adding a control when permission is missing."""
    with patch("authentication_service.get_current_user", return_value=type("User", (), {"username": "testuser", "role": "viewer", "tenant_id": "tenant1"})()):
        mock_rebac.check_permission.return_value = False
        response = client.post(
            "/api/compliance/test-framework/controls",
            json={"id": "CTRL-2", "name": "Test Control 2"},
        )
        assert response.status_code == 403
        assert "Not authorized" in response.json()["detail"]


def test_rebac_check_permission_called():
    """Verify ReBAC check_permission is invoked with correct parameters."""
    with patch("authentication_service.get_current_user", return_value=type("User", (), {"username": "testuser", "role": "admin", "tenant_id": "tenant1"})()):
        mock_rebac.check_permission.return_value = True
        response = client.post(
            "/api/compliance/test-framework/controls",
            json={"id": "CTRL-3", "name": "Test Control 3"},
        )
        assert response.status_code == 200
        # Verify mock was called with expected args
        mock_rebac.check_permission.assert_called_once()
        args = mock_rebac.check_permission.call_args[0]
        assert args[0] == "user:testuser"
        assert args[1] == "add_control"
        assert args[2] == "framework"
        assert args[3] == "test-framework"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])