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


# ===========================================================================
# ITAM-specific roles (ITAM-USR-02, Task 1)
# ===========================================================================

class TestItamRoles:

    def test_itam_admin_can_manage_assets_and_users(self):
        from rbac_service import RBACService
        svc = RBACService()
        user = TokenData(username="a@b.com", role="itam_admin", tenant_id="t1", mfa_verified=True)

        with patch("rbac_service.get_database", return_value=_mock_db(role_doc=None)):
            perms = _run(svc.get_user_permissions(user))

        for expected in ("manage:assets", "manage:licenses", "manage:users", "view:itam",
                          "manage:procurement", "manage:finance"):
            assert expected in perms

    def test_itam_user_has_read_and_request_only(self):
        from rbac_service import RBACService
        svc = RBACService()
        user = TokenData(username="a@b.com", role="itam_user", tenant_id="t1", mfa_verified=True)

        with patch("rbac_service.get_database", return_value=_mock_db(role_doc=None)):
            perms = _run(svc.get_user_permissions(user))

        assert set(perms) == {"view:assets", "view:licenses", "view:itam", "request:assets"}
        assert "manage:assets" not in perms

    def test_itam_viewer_is_read_only(self):
        from rbac_service import RBACService
        svc = RBACService()
        user = TokenData(username="a@b.com", role="itam_viewer", tenant_id="t1", mfa_verified=True)

        with patch("rbac_service.get_database", return_value=_mock_db(role_doc=None)):
            perms = _run(svc.get_user_permissions(user))

        assert set(perms) == {"view:assets", "view:licenses", "view:itam"}

    def test_itam_admin_dependency_grants_manage_assets(self):
        from rbac_service import rbac_service

        user = TokenData(username="a@b.com", role="itam_admin", tenant_id="t1", mfa_verified=True)
        router = APIRouter()

        @router.get("/protected")
        async def protected(u=Depends(rbac_service.has_permission("manage:assets"))):
            return {"ok": True}

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: user

        with patch("rbac_service.get_database", return_value=_mock_db(role_doc=None)):
            with TestClient(app) as client:
                r = client.get("/protected")

        assert r.status_code == 200

    def test_itam_viewer_dependency_denied_manage_assets(self):
        from rbac_service import rbac_service

        user = TokenData(username="a@b.com", role="itam_viewer", tenant_id="t1", mfa_verified=True)
        router = APIRouter()

        @router.get("/protected")
        async def protected(u=Depends(rbac_service.has_permission("manage:assets"))):
            return {"ok": True}

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: user

        with patch("rbac_service.get_database", return_value=_mock_db(role_doc=None)):
            with TestClient(app) as client:
                r = client.get("/protected")

        assert r.status_code == 403


# ===========================================================================
# get_permissions_for_role — synchronous frontend-UI helper (ITAM-USR-02, Task 1)
# ===========================================================================

class TestGetPermissionsForRole:

    def test_returns_permissions_for_known_role(self):
        from rbac_service import RBACService
        svc = RBACService()
        assert "manage:assets" in svc.get_permissions_for_role("itam_admin")

    def test_normalizes_title_case_role(self):
        """The /api/roles UI stub returns Title-Case names ('Admin', 'Viewer')."""
        from rbac_service import RBACService
        svc = RBACService()
        assert svc.get_permissions_for_role("Admin") == svc.get_permissions_for_role("admin")
        assert svc.get_permissions_for_role("Viewer") == svc.get_permissions_for_role("viewer")

    def test_super_admin_gets_wildcard(self):
        from rbac_service import RBACService
        svc = RBACService()
        assert svc.get_permissions_for_role("Super Admin") == ["*"]
        assert svc.get_permissions_for_role("platform-admin") == ["*"]

    def test_unknown_role_returns_empty_list(self):
        from rbac_service import RBACService
        svc = RBACService()
        assert svc.get_permissions_for_role("does_not_exist") == []


# ===========================================================================
# can_assign_role — super-admin assignment guard (ITAM-USR-02, T-64-04)
# ===========================================================================

class TestCanAssignRole:

    def test_non_super_admin_cannot_assign_super_admin(self):
        from rbac_service import RBACService
        svc = RBACService()
        assert svc.can_assign_role("admin", "super_admin") is False
        assert svc.can_assign_role("itam_admin", "Super Admin") is False

    def test_super_admin_can_assign_super_admin(self):
        from rbac_service import RBACService
        svc = RBACService()
        assert svc.can_assign_role("super_admin", "super_admin") is True
        assert svc.can_assign_role("Super Admin", "Super Admin") is True
        assert svc.can_assign_role("platform-admin", "super_admin") is True

    def test_non_elevated_role_assignment_always_allowed(self):
        from rbac_service import RBACService
        svc = RBACService()
        assert svc.can_assign_role("itam_user", "itam_admin") is True
        assert svc.can_assign_role("viewer", "user") is True


# ===========================================================================
# Role normalization — single source of truth (RESEARCH.md Pitfall 3)
# ===========================================================================

def test_role_normalization():
    """'platform-admin' and 'platform_admin' both normalize to 'super_admin',
    closing the "platform-admin gap": a user with either variant gets
    super-admin access through rbac_service's dependency factories.
    """
    from rbac_service import RBACService, rbac_service
    from auth_roles import SUPER_ROLES

    svc = RBACService()

    # Both hyphen and underscore variants normalize to the same canonical key.
    assert svc._normalize_role("platform-admin") == "super_admin"
    assert svc._normalize_role("platform_admin") == "super_admin"
    assert svc._normalize_role("Platform Admin") == "super_admin"

    # auth_roles.SUPER_ROLES (used by raw membership checks across the
    # codebase) includes both the raw and normalized forms.
    assert "platform-admin" in SUPER_ROLES
    assert "platform_admin" in SUPER_ROLES

    # A "platform-admin" user gets full wildcard permissions via the
    # dependency-factory path (get_user_permissions), matching super_admin.
    for variant in ("platform-admin", "platform_admin"):
        user = TokenData(username="p@a.com", role=variant, tenant_id=None, mfa_verified=True)
        with patch("rbac_service.get_database", return_value=_mock_db()):
            perms = _run(rbac_service.get_user_permissions(user))
        assert perms == ["*"], f"Expected wildcard for role={variant!r}"

    # require_role() dependency also recognizes both variants as super-admin,
    # bypassing the allowed-roles allowlist entirely.
    for variant in ("platform-admin", "platform_admin"):
        user = TokenData(username="p@a.com", role=variant, tenant_id=None, mfa_verified=True)
        router = APIRouter()

        @router.get("/protected")
        async def protected(u=Depends(rbac_service.require_role(["itam_admin"]))):
            return {"ok": True}

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda u=user: u

        with TestClient(app) as client:
            r = client.get("/protected")
        assert r.status_code == 200, f"Expected super-admin bypass for role={variant!r}"


# ===========================================================================
# rbac_utils — single normalization path (RESEARCH.md Pitfall 3 / WINDOWS.md #6)
# ===========================================================================
#
# rbac_utils.verify_permission()/is_super_admin() are the actual enforcement
# path used by itam_asset_endpoints._require_itam_admin (which user_endpoints.py
# reuses to admin-gate User CRUD, per 64-01). WINDOWS.md #6 reported that
# role_endpoints.py's /api/roles stub returns Title-Case names ("Admin", "User",
# "Viewer") that resolved to zero permissions through this exact fallback path
# because it did case-sensitive exact-match lookups instead of routing through
# rbac_service._normalize_role(). These tests pin the fix.

class TestRbacUtilsNormalization:

    def _run(self, coro):
        return asyncio.run(coro)

    def test_title_case_admin_resolves_permissions_not_empty(self):
        """WINDOWS.md #6: 'Admin' (from /api/roles stub) must not resolve to zero permissions."""
        import rbac_utils
        user = TokenData(username="a@b.com", role="Admin", tenant_id="t1", mfa_verified=True)

        with patch("rbac_utils.get_database", return_value=_mock_db(role_doc=None)):
            allowed = self._run(rbac_utils.verify_permission(user, "manage:assets"))

        assert allowed is True

    def test_title_case_user_resolves_view_permissions(self):
        import rbac_utils
        user = TokenData(username="a@b.com", role="User", tenant_id="t1", mfa_verified=True)

        with patch("rbac_utils.get_database", return_value=_mock_db(role_doc=None)):
            allowed = self._run(rbac_utils.verify_permission(user, "view:dashboard"))

        assert allowed is True

    def test_title_case_viewer_denied_manage_permission(self):
        """Viewer should still be denied a manage: permission — normalization must
        not accidentally grant more access than the (lowercase) role would have."""
        import rbac_utils
        user = TokenData(username="a@b.com", role="Viewer", tenant_id="t1", mfa_verified=True)

        with patch("rbac_utils.get_database", return_value=_mock_db(role_doc=None)):
            allowed = self._run(rbac_utils.verify_permission(user, "manage:settings"))

        assert allowed is False

    def test_lowercase_admin_behavior_unchanged(self):
        """Regression guard: the pre-existing lowercase-role path must be untouched."""
        import rbac_utils
        user = TokenData(username="a@b.com", role="admin", tenant_id="t1", mfa_verified=True)

        with patch("rbac_utils.get_database", return_value=_mock_db(role_doc=None)):
            allowed = self._run(rbac_utils.verify_permission(user, "manage:assets"))

        assert allowed is True

    def test_tenant_admin_snake_case_still_redirects_to_canonical_entry(self):
        """Regression guard: 'tenant_admin' must still resolve via the 'Tenant Admin' entry."""
        import rbac_utils
        user = TokenData(username="a@b.com", role="tenant_admin", tenant_id="t1", mfa_verified=True)

        with patch("rbac_utils.get_database", return_value=_mock_db(role_doc=None)):
            allowed = self._run(rbac_utils.verify_permission(user, "manage:tenants"))

        assert allowed is True

    def test_is_super_admin_recognizes_platform_admin_underscore_variant(self):
        import rbac_utils
        assert rbac_utils.is_super_admin("platform-admin") is True
        assert rbac_utils.is_super_admin("platform_admin") is True
        assert rbac_utils.is_super_admin("Super Admin") is True
        assert rbac_utils.is_super_admin("nonexistent_role") is False
        assert rbac_utils.is_super_admin(None) is False
