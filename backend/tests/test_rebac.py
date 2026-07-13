"""Phase 36 tests — ReBAC (OpenFGA) authorization on the migrated resource.

add_compliance_control is the single high-value permission check migrated to
ReBAC: the endpoint asks OpenFGA whether user:<username> holds add_control
on framework:<framework_id>, on top of the existing RBAC/tenant checks.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from authentication_service import get_current_user
from auth_types import TokenData
import compliance_framework_mgmt_endpoints as ep_mod


def _make_db():
    db = MagicMock()
    db.compliance_frameworks.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    db.compliance_frameworks.find_one = AsyncMock(return_value=None)
    return db


def _make_client(user=None):
    app = FastAPI()
    app.include_router(ep_mod.router)
    if user is None:
        user = TokenData(username="testuser", role="Super Admin", tenant_id="tenant1", mfa_verified=True)
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _rebac(allow: bool):
    mock = MagicMock()
    mock.check_permission = AsyncMock(return_value=allow)
    return mock


def test_rebac_allow_add_control():
    """ReBAC allows adding a control when OpenFGA grants the relation."""
    db = _make_db()
    rebac = _rebac(True)
    client = _make_client()
    with patch("compliance_framework_mgmt_endpoints.get_database", MagicMock(return_value=db)), \
         patch("compliance_framework_mgmt_endpoints.rebac", rebac):
        response = client.post(
            "/api/compliance/test-framework/controls",
            json={"id": "CTRL-1", "name": "Test Control"},
        )
    assert response.status_code == 200
    assert response.json()["id"] == "CTRL-1"
    db.compliance_frameworks.update_one.assert_awaited_once()


def test_rebac_deny_add_control():
    """ReBAC denies adding a control when OpenFGA refuses the relation."""
    db = _make_db()
    rebac = _rebac(False)
    client = _make_client()
    with patch("compliance_framework_mgmt_endpoints.get_database", MagicMock(return_value=db)), \
         patch("compliance_framework_mgmt_endpoints.rebac", rebac):
        response = client.post(
            "/api/compliance/test-framework/controls",
            json={"id": "CTRL-2", "name": "Test Control 2"},
        )
    assert response.status_code == 403
    assert "Not authorized" in response.json()["detail"]
    # denial happens BEFORE any write
    db.compliance_frameworks.update_one.assert_not_awaited()


def test_rebac_check_permission_called():
    """check_permission receives (user:<name>, relation, object type, object id)."""
    db = _make_db()
    rebac = _rebac(True)
    client = _make_client()
    with patch("compliance_framework_mgmt_endpoints.get_database", MagicMock(return_value=db)), \
         patch("compliance_framework_mgmt_endpoints.rebac", rebac):
        response = client.post(
            "/api/compliance/test-framework/controls",
            json={"id": "CTRL-3", "name": "Test Control 3"},
        )
    assert response.status_code == 200
    rebac.check_permission.assert_awaited_once()
    args = rebac.check_permission.call_args.args
    assert args[0] == "user:testuser"
    assert args[1] == "add_control"
    assert args[2] == "framework"
    assert args[3] == "test-framework"


def test_rebac_missing_fields_still_400():
    """Input validation happens before the ReBAC call."""
    db = _make_db()
    rebac = _rebac(True)
    client = _make_client()
    with patch("compliance_framework_mgmt_endpoints.get_database", MagicMock(return_value=db)), \
         patch("compliance_framework_mgmt_endpoints.rebac", rebac):
        response = client.post(
            "/api/compliance/test-framework/controls",
            json={"name": "no id"},
        )
    assert response.status_code == 400
    rebac.check_permission.assert_not_awaited()
