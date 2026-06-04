"""
Unit tests for RBACService.

Covers:
 - Super admin always gets wildcard permissions
 - Role lookup falls back to hardcoded defaults when DB has no matching role
 - has_permission() dependency grants access for matching permissions
 - has_permission() returns 403 for missing permissions
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi import APIRouter, Depends
from authentication_service import get_current_user
from auth_types import TokenData


# ---------------------------------------------------------------------------
# Helper — run async code in tests
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.run(coro)


def _mock_db(role_doc=None):
    db = MagicMock()
    db.roles = MagicMock()
    db.roles.find_one = AsyncMock(return_value=role_doc)
    return db


# ===========================================================================
# get_user_permissions
# ===========================================================================

class TestGetUserPermissions:

    def test_super_admin_variants_get_wildcard(self):
        from rbac_service import RBACService
        svc = RBACService()

        for role in ("Super Admin", "super_admin", "superadmin", "SUPER_ADMIN"):
            user = TokenData(username="a@b.com", role=role, tenant_id=None, mfa_verified=True)
            with patch("rbac_service.get_database", return_value=_mock_db()):
                perms = _run(svc.get_user_permissions(user))
            assert perms == ["*"], f"Expected wildcard for role={role!r}"

    def test_unknown_role_returns_empty_list(self):
        from rbac_service import RBACService
        svc = RBACService()
        user = TokenData(username="a@b.com", role="nonexistent_role", tenant_id="t1", mfa_verified=True)

        with patch("rbac_service.get_database", return_value=_mock_db(role_doc=None)):
            perms = _run(svc.get_user_permissions(user))

        assert perms == []

    def test_default_user_role_gets_view_dashboard(self):
        from rbac_service import RBACService
        svc = RBACService()
        user = TokenData(username="a@b.com", role="user", tenant_id="t1", mfa_verified=True)

        with patch("rbac_service.get_database", return_value=_mock_db(role_doc=None)):
            perms = _run(svc.get_user_permissions(user))

        assert "view:dashboard" in perms

    def test_db_role_doc_takes_precedence_over_defaults(self):
        from rbac_service import RBACService
        svc = RBACService()
        user = TokenData(username="a@b.com", role="custom_analyst", tenant_id="t1", mfa_verified=True)
        role_doc = {"name": "custom_analyst", "permissions": ["view:threats", "view:security"]}

        with patch("rbac_service.get_database", return_value=_mock_db(role_doc=role_doc)):
            perms = _run(svc.get_user_permissions(user))

        assert perms == ["view:threats", "view:security"]

    def test_admin_role_gets_manage_settings(self):
        from rbac_service import RBACService
        svc = RBACService()
        user = TokenData(username="a@b.com", role="admin", tenant_id="t1", mfa_verified=True)

        with patch("rbac_service.get_database", return_value=_mock_db(role_doc=None)):
            perms = _run(svc.get_user_permissions(user))

        assert "manage:settings" in perms


# ===========================================================================
# has_permission dependency
# ===========================================================================

class TestHasPermission:
    """Tests for the has_permission() FastAPI dependency factory."""

    def _make_app(self, user: TokenData, required_perm: str):
        from rbac_service import rbac_service

        router = APIRouter()

        @router.get("/protected")
        async def protected(u=Depends(rbac_service.has_permission(required_perm))):
            return {"ok": True}

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: user
        return app

    def test_user_with_permission_gets_200(self):
        user = TokenData(username="a@b.com", role="user", tenant_id="t1", mfa_verified=True)
        app = self._make_app(user, "view:dashboard")

        with patch("rbac_service.get_database", return_value=_mock_db(role_doc=None)):
            with TestClient(app) as client:
                r = client.get("/protected")

        assert r.status_code == 200

    def test_user_missing_permission_gets_403(self):
        user = TokenData(username="a@b.com", role="viewer", tenant_id="t1", mfa_verified=True)
        app = self._make_app(user, "manage:settings")

        with patch("rbac_service.get_database", return_value=_mock_db(role_doc=None)):
            with TestClient(app) as client:
                r = client.get("/protected")

        assert r.status_code == 403

    def test_super_admin_bypasses_all_permission_checks(self):
        user = TokenData(username="s@p.com", role="Super Admin", tenant_id=None, mfa_verified=True)
        app = self._make_app(user, "manage:nuclear_launch_codes")

        with patch("rbac_service.get_database", return_value=_mock_db(role_doc=None)):
            with TestClient(app) as client:
                r = client.get("/protected")

        assert r.status_code == 200

    def test_wildcard_permission_grants_everything(self):
        """A role doc with ['*'] should satisfy any required permission."""
        user = TokenData(username="a@b.com", role="god_mode", tenant_id="t1", mfa_verified=True)
        role_doc = {"name": "god_mode", "permissions": ["*"]}
        app = self._make_app(user, "manage:settings")

        with patch("rbac_service.get_database", return_value=_mock_db(role_doc=role_doc)):
            with TestClient(app) as client:
                r = client.get("/protected")

        assert r.status_code == 200
