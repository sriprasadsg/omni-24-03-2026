"""
Tests for trust_service.py and trust_endpoints.py (Public Trust Center).

Wave 0 scaffold (plan 29-01): persistence, tenant-isolation, and admin-auth
suites for the DB-backed trust_service. Public-route tests (public_get,
public_post, rate_limit, private_doc_filter, custom_domain) are added in
plan 29-02/29-03 in this same file.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from authentication_service import get_current_user
from auth_types import TokenData


# ─── helpers (cloned verbatim from test_automation_and_baa.py) ────────────────

def _col(**overrides):
    col = MagicMock()
    col.find_one   = AsyncMock(return_value=None)
    col.insert_one = AsyncMock()
    col.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
    col.delete_one = AsyncMock()
    col.find       = MagicMock()
    col.find.return_value.to_list = AsyncMock(return_value=[])
    col.find.return_value.sort    = MagicMock(return_value=MagicMock())
    col.find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
    for k, v in overrides.items():
        setattr(col, k, v)
    return col


def _db(**collections):
    db = MagicMock()
    db.__getitem__ = lambda self, name: getattr(self, name, _col())
    for name, col in collections.items():
        setattr(db, name, col)
    return db


def _user(role="security_analyst", tenant_id="t1"):
    return TokenData(username="test@example.com", role=role, tenant_id=tenant_id, mfa_verified=True)


def _app(router, user):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    return app


# ─── TRUST-01: persistence ─────────────────────────────────────────────────────

class TestTrustPersistence:

    @pytest.mark.asyncio
    async def test_profile_persists_across_fresh_db_handle(self):
        """A profile saved via update_profile must round-trip through a fresh
        get_database() read — not a Python-process singleton."""
        import trust_service

        saved_doc = {}

        async def fake_update_one(filter, update, *args, **kwargs):
            saved_doc.update(update.get("$set", {}))
            return MagicMock(matched_count=1)

        async def fake_find_one(filter=None, *args, **kwargs):
            return dict(saved_doc) if saved_doc else None

        col = _col()
        col.update_one = AsyncMock(side_effect=fake_update_one)
        col.find_one = AsyncMock(side_effect=fake_find_one)
        db = _db(trust_profiles=col)

        updates = {"company_name": "Acme Corp", "description": "Persisted profile"}
        await trust_service.update_profile(db, "t1", updates)

        # Simulate a "restart" — read again on a fresh call, same underlying db handle
        result = await trust_service.get_profile(db, "t1")

        assert col.update_one.called
        call_kwargs = col.update_one.call_args.kwargs
        assert call_kwargs.get("upsert") is True
        assert result["company_name"] == "Acme Corp"
        assert result["description"] == "Persisted profile"


# ─── TRUST-01: tenant isolation ────────────────────────────────────────────────

class TestTrustTenantIsolation:

    @pytest.mark.asyncio
    async def test_profile_query_is_tenant_scoped_not_exempt(self):
        """get_profile/get_requests must read db.trust_profiles/db.trust_access_requests
        (the TenantIsolatedCollection-wrapped path) — these two collections must
        never appear in database.py's global-exemption allowlist."""
        import trust_service
        import database

        exempt_names = set()
        # database.py hardcodes its exemption list inline in two places (__getattr__/__getitem__)
        # of TenantIsolatedDatabase; read the source to assert trust collections are absent.
        src = open(os.path.join(os.path.dirname(database.__file__), "database.py")).read()
        assert "trust_profiles" not in src
        assert "trust_access_requests" not in src

        profile_col = _col()
        requests_col = _col()
        db = _db(trust_profiles=profile_col, trust_access_requests=requests_col)

        await trust_service.get_profile(db, "t1")
        assert profile_col.find_one.called

        await trust_service.get_requests(db, "t1")
        assert requests_col.find.called


# ─── TRUST-01/02: admin auth (unchanged auth model) ────────────────────────────

class TestTrustAdminAuth:

    def test_admin_auth_requires_admin_role_for_profile_update(self):
        from trust_endpoints import router
        db = _db(trust_profiles=_col(), trust_access_requests=_col())
        app = _app(router, _user(role="security_analyst"))
        with patch("trust_endpoints.get_database", return_value=db):
            res = TestClient(app).put("/api/trust-center/profile", json={"company_name": "X"})
        assert res.status_code == 403

    def test_admin_auth_allows_admin_role_for_profile_update(self):
        from trust_endpoints import router
        db = _db(trust_profiles=_col(), trust_access_requests=_col())
        app = _app(router, _user(role="admin"))
        with patch("trust_endpoints.get_database", return_value=db):
            res = TestClient(app).put("/api/trust-center/profile", json={"company_name": "X"})
        assert res.status_code == 200

    def test_admin_auth_rejects_unauthenticated_profile_update(self):
        from trust_endpoints import router
        app = FastAPI()
        app.include_router(router)
        # No dependency_overrides[get_current_user] — unauthenticated
        res = TestClient(app).put("/api/trust-center/profile", json={"company_name": "X"})
        assert res.status_code in (401, 403)
