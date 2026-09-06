"""ITAM-API-01 auth-spine regression suite (Phase 73 Plan 01).

Task 1 — the tracer: an API-key-authenticated caller checks an asset out
over HTTP, the call is narrowed by the key's scopes, and the checkout fires
`asset.checked_out` without blocking the response. Tasks 2/3 extend this
same module with the excluded-surfaces, session-parity, scope-narrowing and
rate-limit regressions (selectable via `-k excluded_surfaces`,
`-k catalog_scope_narrowing`, `-k session_auth`, `-k scoped_key_allowed`,
`-k scope_narrowing_enforced`, `-k rate_limit`).

Shared fixtures/helpers live in itam_api_integrations_test_support.py (split
out to keep this module under the CLAUDE.md 500-line limit, following the
itam_finance_test_support.py precedent).

Conventions (this repository, not reinvented here): backend modules are
imported by bare name (never a `backend.` prefix); FastAPI dependencies are
swapped via `app.dependency_overrides`, never module-level patching of a
`Depends`-captured callable.
"""
import asyncio
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.itam_api_integrations_test_support import (  # noqa: F401 — fixtures re-exported for pytest
    FAKE_API_KEY,
    _reset_api_key_rate_limiter,
    _EmptyAsyncCursor,
    _chainable_cursor,
    MockTenantIsolatedDatabase,
    mock_db,
    patch_lifecycle_database,
    lifecycle_app,
    _api_key_token,
    _api_key_dependency_override,
    deployable_asset,
    patch_rbac_utils_db,
    _session_admin_token,
    _api_key_only_app,
    _session_app,
    _build_route_case,
    _catalog_list_db,
)

from auth_types import TokenData
from auth_utils import hash_password
import api_key_auth
from api_key_auth import get_current_user_or_api_key
from itam_webhook_events import EVENT_ASSET_CHECKED_OUT
import itam_catalog_endpoints
import ldap_endpoints
import api_key_endpoints
import sso_endpoints
import user_endpoints


# ─── Task 1: the tracer ───────────────────────────────────────────────────

class TestTracerApiKeyCheckoutFiresWebhook:
    @pytest.mark.asyncio
    async def test_tracer_api_key_checkout_fires_webhook(self, mock_db, lifecycle_app):
        mock_db.assets.find_one_and_update = AsyncMock(return_value=deployable_asset())
        mock_db.users.find_one = AsyncMock(return_value={"id": "user-7", "email": "u7@x.com"})
        mock_db.assignment_history.insert_one = AsyncMock(return_value=MagicMock(inserted_id="hist-1"))

        token = _api_key_token(scopes=["manage:assets"])
        lifecycle_app.dependency_overrides[get_current_user_or_api_key] = _api_key_dependency_override(
            FAKE_API_KEY, token
        )

        recorder = AsyncMock()
        with patch("webhook_service.WebhookService.trigger_webhook", recorder):
            transport = ASGITransport(app=lifecycle_app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
                r = await ac.post(
                    "/api/assets/asset-1/checkout",
                    json={"targetType": "user", "targetId": "user-7"},
                    headers={"X-API-Key": FAKE_API_KEY},
                )
            # asyncio.create_task only schedules the dispatch — yield control
            # back to the loop so it actually runs before we assert on it.
            for _ in range(5):
                await asyncio.sleep(0)

        assert r.status_code == 200, r.text

        recorder.assert_awaited_once()
        args, _kwargs = recorder.call_args
        assert args[0] == EVENT_ASSET_CHECKED_OUT
        payload = args[1]
        assert "before" in payload and "after" in payload
        assert payload["before"]["lifecycleStatus"] != payload["after"]["lifecycleStatus"]
        assert payload["after"]["lifecycleStatus"] == "deployed"

    @pytest.mark.asyncio
    async def test_tracer_wrong_api_key_refused(self, mock_db, lifecycle_app):
        """Sanity check on the fixture itself: an unrecognized key never
        reaches the route body (401, not 200/403)."""
        token = _api_key_token(scopes=["manage:assets"])
        lifecycle_app.dependency_overrides[get_current_user_or_api_key] = _api_key_dependency_override(
            FAKE_API_KEY, token
        )

        transport = ASGITransport(app=lifecycle_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post(
                "/api/assets/asset-1/checkout",
                json={"targetType": "user", "targetId": "user-7"},
                headers={"X-API-Key": "not-the-right-key"},
            )
        assert r.status_code == 401


# ─── Task 2: the four excluded surfaces refuse API-key auth, admins keep working ──

class TestExcludedSurfacesRefuseApiKey:
    """A request carrying only an API key never reaches the four non-ITAM
    surfaces the user explicitly excluded from D-02; a session-authenticated
    admin still works on each one unchanged."""

    @pytest.mark.asyncio
    async def test_excluded_surfaces_ldap_config(self, monkeypatch, patch_rbac_utils_db):
        from tests.conftest import _make_col
        db = MagicMock()
        db.ldap_configs = _make_col(find_one=AsyncMock(return_value=None))

        api_key_app = _api_key_only_app(ldap_endpoints.router)
        transport = ASGITransport(app=api_key_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/admin/ldap/config")
        assert r.status_code in (401, 403)

        monkeypatch.setattr(ldap_endpoints, "get_database", lambda: db)
        session_app = _session_app(ldap_endpoints.router)
        transport = ASGITransport(app=session_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/admin/ldap/config")
        assert r.status_code not in (401, 403)

    @pytest.mark.asyncio
    async def test_excluded_surfaces_api_key_admin_list(self, monkeypatch, patch_rbac_utils_db):
        api_key_app = _api_key_only_app(api_key_endpoints.admin_router)
        transport = ASGITransport(app=api_key_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/admin/api-keys")
        assert r.status_code in (401, 403)

        mock_mongodb = MagicMock()
        mock_mongodb.db.users.find = MagicMock(return_value=_EmptyAsyncCursor())
        monkeypatch.setattr(api_key_endpoints, "mongodb", mock_mongodb)
        session_app = _session_app(api_key_endpoints.admin_router)
        transport = ASGITransport(app=session_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/admin/api-keys")
        assert r.status_code not in (401, 403)

    @pytest.mark.asyncio
    async def test_excluded_surfaces_sso_saml_config(self, monkeypatch, patch_rbac_utils_db):
        from tests.conftest import _make_col
        db = MagicMock()
        db.saml_configs = _make_col(find_one=AsyncMock(return_value=None))

        api_key_app = _api_key_only_app(sso_endpoints.saml_router)
        transport = ASGITransport(app=api_key_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/admin/sso/saml/config")
        assert r.status_code in (401, 403)

        monkeypatch.setattr(sso_endpoints, "get_database", lambda: db)
        session_app = _session_app(sso_endpoints.saml_router)
        transport = ASGITransport(app=session_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/admin/sso/saml/config")
        assert r.status_code not in (401, 403)

    @pytest.mark.asyncio
    async def test_excluded_surfaces_user_management_list(self, monkeypatch, patch_rbac_utils_db):
        from tests.conftest import _make_col
        db = MagicMock()
        db.users = _make_col(
            count_documents=AsyncMock(return_value=0),
            find=MagicMock(return_value=_chainable_cursor([])),
        )

        api_key_app = _api_key_only_app(user_endpoints.router)
        transport = ASGITransport(app=api_key_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/users")
        assert r.status_code in (401, 403)

        monkeypatch.setattr(user_endpoints, "get_database", lambda: db)
        monkeypatch.setattr(user_endpoints, "get_tenant_id", lambda: "tenant-a")
        session_app = _session_app(user_endpoints.router)
        transport = ASGITransport(app=session_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.get("/api/users")
        assert r.status_code not in (401, 403)


# ─── Task 2: catalog router's independent duplicate guard is scope-narrowed ──

class TestCatalogScopeNarrowing:
    @pytest.mark.asyncio
    async def test_catalog_scope_narrowing_read_only_key_refused_manage_key_allowed(self, monkeypatch, patch_rbac_utils_db):
        from tests.conftest import _make_col
        db = MagicMock()
        db.manufacturers = _make_col(insert_one=AsyncMock(return_value=MagicMock(inserted_id="mock-id")))
        # create_catalog_entity resolves the collection via db[collection_name]
        # subscript access, not attribute access.
        db.__getitem__ = MagicMock(side_effect=lambda name: getattr(db, name))
        monkeypatch.setattr(itam_catalog_endpoints, "get_database", lambda: db)
        monkeypatch.setattr(itam_catalog_endpoints, "log_itam_action", AsyncMock())

        app = FastAPI()
        app.include_router(itam_catalog_endpoints.router)

        read_only_token = TokenData(
            username="svc-key@tenant-a", role="admin", tenant_id="tenant-a",
            scopes=["read:assets"], auth_source="api_key",
        )
        app.dependency_overrides[get_current_user_or_api_key] = lambda: read_only_token
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/itam/catalog/manufacturers", json={"name": "Acme Corp"})
        assert r.status_code == 403
        assert "scope" in r.json()["detail"].lower()

        manage_token = TokenData(
            username="svc-key@tenant-a", role="admin", tenant_id="tenant-a",
            scopes=["manage:assets"], auth_source="api_key",
        )
        app.dependency_overrides[get_current_user_or_api_key] = lambda: manage_token
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/itam/catalog/manufacturers", json={"name": "Acme Corp"})
        assert r.status_code == 201, r.text


# ─── Task 3: ITAM-API-01 regression suite ────────────────────────────────
# session parity / scoped-key-allowed / scope-narrowing-enforced / rate-limit,
# selectors match 73-VALIDATION.md verbatim.

class TestSessionAuthRegression:
    """D-01 regression: session (JWT) auth still works unchanged on every
    _require_itam_admin-gated route family, no API key present."""

    @pytest.mark.parametrize("which", ["asset", "lifecycle", "catalog", "reporting"])
    @pytest.mark.asyncio
    async def test_session_auth_still_works(self, which, monkeypatch):
        app, method, path, kwargs = _build_route_case(monkeypatch, which)
        # _require_itam_admin now resolves through get_current_user_or_api_key
        # (D-01) — a real session caller arrives there via its `elif token`
        # branch (verify_token_async), so the session identity is injected at
        # that dependency, not the now-bypassed get_current_user. scopes=None
        # / auth_source="session" is exactly what a real JWT caller carries.
        session_token = TokenData(
            username="admin@example.com", role="admin", tenant_id="tenant-a",
            scopes=None, auth_source="session",
        )
        app.dependency_overrides[get_current_user_or_api_key] = lambda: session_token
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await getattr(ac, method)(path, **kwargs)
        assert r.status_code not in (401, 403), r.text


class TestScopedKeyAllowed:
    """A key whose scopes contain manage:assets succeeds on the same routes."""

    @pytest.mark.parametrize("which", ["asset", "lifecycle", "catalog", "reporting"])
    @pytest.mark.asyncio
    async def test_scoped_key_allowed(self, which, monkeypatch):
        app, method, path, kwargs = _build_route_case(monkeypatch, which)
        token = _api_key_token(scopes=["manage:assets"])
        app.dependency_overrides[get_current_user_or_api_key] = lambda: token
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await getattr(ac, method)(path, **kwargs)
        assert r.status_code not in (401, 403), r.text

    @pytest.mark.asyncio
    async def test_scoped_key_allowed_wildcard_scope(self, monkeypatch):
        app, method, path, kwargs = _build_route_case(monkeypatch, "lifecycle")
        token = _api_key_token(scopes=["*"])
        app.dependency_overrides[get_current_user_or_api_key] = lambda: token
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await getattr(ac, method)(path, **kwargs)
        assert r.status_code not in (401, 403), r.text


class TestScopeNarrowingEnforced:
    """RESEARCH.md Pitfall 1 — the security regression: written so it would
    fail if the narrowing check were ever removed."""

    @pytest.mark.asyncio
    async def test_scope_narrowing_enforced_read_only_key_refused_on_canonical_guard(self, monkeypatch):
        app, method, path, kwargs = _build_route_case(monkeypatch, "lifecycle")
        token = _api_key_token(scopes=["read:assets"])
        app.dependency_overrides[get_current_user_or_api_key] = lambda: token
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await getattr(ac, method)(path, **kwargs)
        assert r.status_code == 403
        assert "manage:assets" in r.json()["detail"]

    @pytest.mark.asyncio
    async def test_scope_narrowing_enforced_read_only_key_refused_on_catalog_guard(self, monkeypatch):
        db = _catalog_list_db()
        monkeypatch.setattr(itam_catalog_endpoints, "verify_permission", AsyncMock(return_value=True))
        monkeypatch.setattr(itam_catalog_endpoints, "get_database", lambda: db)
        app = FastAPI()
        app.include_router(itam_catalog_endpoints.router)
        token = _api_key_token(scopes=["read:assets"])
        app.dependency_overrides[get_current_user_or_api_key] = lambda: token
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await ac.post("/api/itam/catalog/manufacturers", json={"name": "Acme"})
        assert r.status_code == 403
        assert "scope" in r.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_scope_narrowing_enforced_empty_scopes_denies(self, monkeypatch):
        app, method, path, kwargs = _build_route_case(monkeypatch, "lifecycle")
        token = _api_key_token(scopes=[])
        app.dependency_overrides[get_current_user_or_api_key] = lambda: token
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await getattr(ac, method)(path, **kwargs)
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_scope_narrowing_enforced_none_scopes_session_allows(self, monkeypatch):
        """The other end of _scopes_allow's contract: scopes=None (session
        auth) is never narrowed, even when the identity arrives through the
        get_current_user_or_api_key dependency (as a real session caller's
        request would)."""
        app, method, path, kwargs = _build_route_case(monkeypatch, "lifecycle")
        token = TokenData(
            username="admin@example.com", role="admin", tenant_id="tenant-a",
            scopes=None, auth_source="session",
        )
        app.dependency_overrides[get_current_user_or_api_key] = lambda: token
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r = await getattr(ac, method)(path, **kwargs)
        assert r.status_code not in (401, 403), r.text


class TestRateLimit:
    """D-04: reuse the existing per-key rate limiter as-is — no ITAM-specific
    tier. Drives the REAL api_key_auth auth path (no dependency override)
    through an ITAM route until it 429s."""

    @pytest.mark.asyncio
    async def test_rate_limit_429_via_itam_route(self, monkeypatch):
        plaintext = "omni_pat_test_ratelimit_key_1234"
        key_doc = {
            "id": "pat-rate-1",
            "name": "Rate Limit Test Key",
            "keyPrefix": plaintext[:12],
            "keyHash": hash_password(plaintext),
            "scopes": ["manage:assets"],
            "rateLimit": 2,
            "revokedAt": None,
            "expiresAt": None,
        }
        user_doc = {
            "email": "svc@tenant-a", "username": "svc@tenant-a",
            "role": "admin", "tenantId": "tenant-a", "apiKeys": [key_doc],
        }
        mock_mongodb = MagicMock()
        mock_mongodb.db.users.find_one = AsyncMock(return_value=user_doc)
        mock_mongodb.db.users.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
        monkeypatch.setattr(api_key_auth, "mongodb", mock_mongodb)

        app, method, path, kwargs = _build_route_case(monkeypatch, "lifecycle")
        # Real get_current_user_or_api_key path this time — no dependency
        # override — so the request must carry the header and actually run
        # api_key_auth._check_rate_limit.
        kwargs = dict(kwargs)
        kwargs["headers"] = {"X-API-Key": plaintext}

        transport = ASGITransport(app=app)
        statuses = []
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            for _ in range(4):
                r = await getattr(ac, method)(path, **kwargs)
                statuses.append(r.status_code)

        assert 429 in statuses, statuses
        # The 429 must come from api_key_auth's own limiter, not a bespoke
        # ITAM-specific tier (D-04) — confirmed by construction: no other
        # rate-limit mechanism is wired into this router.
