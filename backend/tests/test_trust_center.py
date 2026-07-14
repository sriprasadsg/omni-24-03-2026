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
        db = _db(trust_profiles=_col(), trust_access_requests=_col(), tenants=_col())
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


# ─── TRUST-01/03: trust_slug / trust_domain settings surfaced by admin routes ──

class TestTrustAdminSettings:

    def test_put_trust_domain_persists_to_tenants_and_get_returns_it(self):
        from trust_endpoints import router

        tenants_col = _col()
        # First find_one call (inside PUT's trust_domain branch check via
        # _ensure_trust_slug) returns a tenant that already has trust_domain set,
        # simulating the persisted state after the update_one write.
        tenants_col.find_one = AsyncMock(
            return_value={"trust_slug": "trust-abc123def456", "trust_domain": "trust.acme.com"}
        )
        db = _db(trust_profiles=_col(), trust_access_requests=_col(), tenants=tenants_col)
        app = _app(router, _user(role="admin"))

        with patch("trust_endpoints.get_database", return_value=db):
            put_res = TestClient(app).put(
                "/api/trust-center/profile", json={"trust_domain": "trust.acme.com"}
            )
            assert put_res.status_code == 200
            assert tenants_col.update_one.called
            update_call = tenants_col.update_one.call_args
            assert update_call.args[1]["$set"]["trust_domain"] == "trust.acme.com"

            get_res = TestClient(app).get("/api/trust-center/profile")
            assert get_res.status_code == 200
            body = get_res.json()
            assert body["trust_slug"] == "trust-abc123def456"
            assert body["trust_domain"] == "trust.acme.com"


# ─── TRUST-02: public GET route (no auth) ──────────────────────────────────────

def _public_app():
    """Minimal FastAPI app carrying only the genuinely public trust router.
    No get_current_user override — a real TestClient call proves no auth is
    required and also exercises the slowapi response: Response wiring."""
    from trust_endpoints import public_router
    app = FastAPI()
    app.include_router(public_router)
    return app


_SEEDED_PROFILE = {
    "company_name": "Acme Corp",
    "description": "We take security seriously.",
    "contact_email": "trust@acme.com",
    "logo_url": "https://acme.com/logo.png",
    "compliance_frameworks": ["SOC2", "ISO27001"],
    "public_documents": [{"name": "Security Whitepaper", "url": "https://acme.com/whitepaper.pdf"}],
    "private_documents": [
        {"name": "SOC2 Type II Report", "url": "https://acme.com/private/soc2.pdf"},
        {"name": "Pen Test Summary", "url": "https://acme.com/private/pentest.pdf"},
    ],
}


class TestPublicTrustGet:

    def test_public_get_no_auth_header_returns_200_for_known_slug(self):
        tenants_col = _col()
        tenants_col.find_one = AsyncMock(
            side_effect=lambda filt, *a, **kw: (
                {"id": "t1"} if filt.get("trust_slug") == "trust-abc123" else None
            )
        )
        profile_col = _col()
        profile_col.find_one = AsyncMock(return_value=dict(_SEEDED_PROFILE))
        db = _db(tenants=tenants_col, trust_profiles=profile_col)
        app = _public_app()

        with patch("trust_endpoints.get_database", return_value=db):
            res = TestClient(app).get("/api/public/trust/trust-abc123")

        assert res.status_code == 200
        body = res.json()
        assert body["company_name"] == "Acme Corp"

    def test_public_get_unknown_slug_returns_clean_404(self):
        tenants_col = _col()
        tenants_col.find_one = AsyncMock(return_value=None)
        db = _db(tenants=tenants_col, trust_profiles=_col())
        app = _public_app()

        with patch("trust_endpoints.get_database", return_value=db):
            res = TestClient(app).get("/api/public/trust/does-not-exist")

        assert res.status_code == 404
        assert res.json()["detail"] == "Not found"


class TestPublicDocFilter:

    def test_private_doc_filter_no_url_key(self):
        tenants_col = _col()
        tenants_col.find_one = AsyncMock(return_value={"id": "t1"})
        profile_col = _col()
        profile_col.find_one = AsyncMock(return_value=dict(_SEEDED_PROFILE))
        db = _db(tenants=tenants_col, trust_profiles=profile_col)
        app = _public_app()

        with patch("trust_endpoints.get_database", return_value=db):
            res = TestClient(app).get("/api/public/trust/trust-abc123")

        assert res.status_code == 200
        body = res.json()
        assert len(body["private_documents"]) == 2
        for entry in body["private_documents"]:
            assert set(entry.keys()) == {"name"}
            assert "url" not in entry
        # Public documents are untouched — URLs still present.
        assert body["public_documents"][0]["url"] == "https://acme.com/whitepaper.pdf"


class TestCustomDomainResolution:

    def test_custom_domain_matching_host_resolves_tenant_over_mismatched_slug(self):
        tenants_col = _col()

        async def fake_find_one(filt, *a, **kw):
            if filt.get("trust_domain") == "trust.acme.com":
                return {"id": "t1"}
            return None

        tenants_col.find_one = AsyncMock(side_effect=fake_find_one)
        profile_col = _col()
        profile_col.find_one = AsyncMock(return_value=dict(_SEEDED_PROFILE))
        db = _db(tenants=tenants_col, trust_profiles=profile_col)
        app = _public_app()

        with patch("trust_endpoints.get_database", return_value=db):
            res = TestClient(app).get(
                "/api/public/trust/totally-wrong-slug",
                headers={"Host": "trust.acme.com"},
            )

        assert res.status_code == 200
        assert res.json()["company_name"] == "Acme Corp"

    def test_custom_domain_unrecognized_host_falls_back_to_slug_lookup(self):
        tenants_col = _col()

        async def fake_find_one(filt, *a, **kw):
            if filt.get("trust_domain"):
                return None  # unrecognized Host
            if filt.get("trust_slug") == "trust-abc123":
                return {"id": "t1"}
            return None

        tenants_col.find_one = AsyncMock(side_effect=fake_find_one)
        profile_col = _col()
        profile_col.find_one = AsyncMock(return_value=dict(_SEEDED_PROFILE))
        db = _db(tenants=tenants_col, trust_profiles=profile_col)
        app = _public_app()

        with patch("trust_endpoints.get_database", return_value=db):
            res = TestClient(app).get(
                "/api/public/trust/trust-abc123",
                headers={"Host": "unrelated.example.com"},
            )

        assert res.status_code == 200
        assert res.json()["company_name"] == "Acme Corp"


# ─── TRUST-02: public POST access-request (no auth, NDA consent) ──────────────

def _tenants_col_for_slug(slug="trust-abc123", tenant_id="t1"):
    col = _col()

    async def fake_find_one(filt, *a, **kw):
        if filt.get("trust_slug") == slug:
            return {"id": tenant_id}
        return None

    col.find_one = AsyncMock(side_effect=fake_find_one)
    return col


class TestPublicAccessRequestPost:

    def test_public_post_valid_consent_inserts_pending_request(self):
        tenants_col = _tenants_col_for_slug()
        requests_col = _col()
        db = _db(tenants=tenants_col, trust_access_requests=requests_col)
        app = _public_app()

        payload = {
            "requester_email": "visitor@example.com",
            "company": "Example Inc",
            "reason": "Due diligence review",
            "consent": True,
        }
        with patch("trust_endpoints.get_database", return_value=db):
            res = TestClient(app).post(
                "/api/public/trust/trust-abc123/requests",
                json=payload,
                headers={"User-Agent": "pytest-agent/1.0"},
            )

        assert res.status_code == 200
        assert res.json() == {"success": True}
        assert requests_col.insert_one.called
        inserted = requests_col.insert_one.call_args.args[0]
        assert inserted["status"] == "Pending"
        assert inserted["requester_email"] == "visitor@example.com"
        assert inserted["consented"] is True
        assert inserted["user_agent"] == "pytest-agent/1.0"
        assert "ip_address" in inserted
        assert "requested_at" in inserted

    def test_public_post_missing_consent_returns_400_and_inserts_nothing(self):
        tenants_col = _tenants_col_for_slug()
        requests_col = _col()
        db = _db(tenants=tenants_col, trust_access_requests=requests_col)
        app = _public_app()

        payload = {
            "requester_email": "visitor@example.com",
            "company": "Example Inc",
            "reason": "Due diligence review",
            "consent": False,
        }
        with patch("trust_endpoints.get_database", return_value=db):
            res = TestClient(app).post("/api/public/trust/trust-abc123/requests", json=payload)

        assert res.status_code == 400
        assert "consent" in res.json()["detail"].lower()
        assert not requests_col.insert_one.called

    def test_public_post_consent_absent_defaults_false_returns_400(self):
        tenants_col = _tenants_col_for_slug()
        requests_col = _col()
        db = _db(tenants=tenants_col, trust_access_requests=requests_col)
        app = _public_app()

        payload = {
            "requester_email": "visitor@example.com",
            "company": "Example Inc",
            "reason": "Due diligence review",
        }
        with patch("trust_endpoints.get_database", return_value=db):
            res = TestClient(app).post("/api/public/trust/trust-abc123/requests", json=payload)

        assert res.status_code == 400
        assert not requests_col.insert_one.called

    def test_public_post_forged_metadata_ignored_server_values_win(self):
        tenants_col = _tenants_col_for_slug()
        requests_col = _col()
        db = _db(tenants=tenants_col, trust_access_requests=requests_col)
        app = _public_app()

        payload = {
            "requester_email": "visitor@example.com",
            "company": "Example Inc",
            "reason": "Due diligence review",
            "consent": True,
            # Forged fields — not part of AccessRequestCreate's schema, so
            # FastAPI/Pydantic silently ignores them; asserted below.
            "ip_address": "1.2.3.4",
            "user_agent": "forged-agent",
            "requested_at": "1999-01-01T00:00:00+00:00",
        }
        with patch("trust_endpoints.get_database", return_value=db):
            res = TestClient(app).post(
                "/api/public/trust/trust-abc123/requests",
                json=payload,
                headers={"User-Agent": "real-browser-ua/2.0"},
            )

        assert res.status_code == 200
        inserted = requests_col.insert_one.call_args.args[0]
        assert inserted["ip_address"] != "1.2.3.4"
        assert inserted["user_agent"] == "real-browser-ua/2.0"
        assert inserted["requested_at"] != "1999-01-01T00:00:00+00:00"
