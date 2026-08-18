"""Shared test support for the ITAM-API-01 auth-spine suite (Phase 73 Plan 01,
Task 3's own fallback: split out of test_itam_api_integrations.py to keep that
module under the CLAUDE.md 500-line limit, following the itam_finance_test_support.py
precedent).

Fixtures/helpers here cover: a tenant-scoped mock DB (mirrors
itam_lifecycle_test_support.py), the api-key-vs-session dependency-override
builders used across Tasks 1-3, and the per-router-family test-app builder
Task 3 uses for its session_auth / scoped_key_allowed / scope_narrowing_enforced
parametrized routes.

This module is deliberately not named `test_*.py` so pytest does not try to
collect it directly.
"""
import sys
import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, Header, HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.conftest import make_test_app, make_token_data, _make_col

from auth_types import TokenData
from authentication_service import get_current_user
import api_key_auth
from api_key_auth import get_current_user_or_api_key
import itam_lifecycle_endpoints
import itam_asset_endpoints
import itam_catalog_endpoints
import itam_reporting_endpoints
import ldap_endpoints
import api_key_endpoints
import sso_endpoints
import user_endpoints

FAKE_API_KEY = "test-omni-pat-fixture-key"


@pytest.fixture(autouse=True)
def _reset_api_key_rate_limiter():
    """The per-key rate limiter (api_key_auth._usage_windows) is a
    process-global singleton — reset before and after every test in this
    module so hit counts never bleed between tests (this repository has
    been bitten by exactly that with the shared slowapi limiter before)."""
    api_key_auth._usage_windows.clear()
    yield
    api_key_auth._usage_windows.clear()


class _EmptyAsyncCursor:
    """Minimal async-iterable cursor stand-in for `async for x in db.col.find(...)`."""

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


def _chainable_cursor(items):
    cursor = MagicMock()
    cursor.skip.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.to_list = AsyncMock(return_value=items)
    return cursor


# ─── Shared tenant-scoped mock DB (mirrors itam_lifecycle_test_support.py) ───

class MockTenantIsolatedCollection:
    def __init__(self, tenant_id, raw_collection_mock):
        self._tenant_id = tenant_id
        self._raw_collection = raw_collection_mock

        async def _find_one(f, *args, **kwargs):
            return await raw_collection_mock.find_one({**(f or {}), "tenantId": self._tenant_id}, *args, **kwargs)

        async def _insert_one(doc, *args, **kwargs):
            return await raw_collection_mock.insert_one({**doc, "tenantId": self._tenant_id}, *args, **kwargs)

        async def _find_one_and_update(f, u, *args, **kwargs):
            return await raw_collection_mock.find_one_and_update({**(f or {}), "tenantId": self._tenant_id}, u, *args, **kwargs)

        self.find_one = _find_one
        self.insert_one = _insert_one
        self.find_one_and_update = _find_one_and_update
        self.find = MagicMock(side_effect=lambda f=None, *args, **kwargs:
                               raw_collection_mock.find({**(f if f else {}), "tenantId": self._tenant_id}, *args, **kwargs))


class MockTenantIsolatedDatabase:
    def __init__(self, raw_db_mock, tenant_id):
        self._raw_db = raw_db_mock
        self._tenant_id = tenant_id

    def __getattr__(self, name):
        return MockTenantIsolatedCollection(self._tenant_id, getattr(self._raw_db, name))

    def __getitem__(self, name):
        return self.__getattr__(name)


@pytest.fixture
def mock_db():
    db = MagicMock()
    for name in ("assets", "users", "locations", "assignment_history", "roles"):
        setattr(db, name, _make_col())
    db.assets.find_one_and_update = AsyncMock(return_value=None)
    _history_cursor = MagicMock()
    _history_cursor.sort.return_value = _history_cursor
    _history_cursor.limit.return_value = _history_cursor
    _history_cursor.to_list = AsyncMock(return_value=[])
    db.assignment_history.find = MagicMock(return_value=_history_cursor)
    return db


@pytest.fixture
def patch_lifecycle_database(mock_db, monkeypatch):
    def get_mock_tenant_db():
        return MockTenantIsolatedDatabase(mock_db, "tenant-a")
    monkeypatch.setattr(itam_lifecycle_endpoints, "get_database", get_mock_tenant_db)
    return get_mock_tenant_db


@pytest.fixture
def lifecycle_app(mock_db, patch_lifecycle_database, monkeypatch):
    """Test app mounting only itam_lifecycle_endpoints.router, real auth spine
    intact (_require_itam_admin is NOT bypassed — only its inner role check,
    verify_permission, is stubbed True so the test exercises the scope
    narrowing this plan adds without needing a real db.roles document)."""
    monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=True))
    monkeypatch.setattr(itam_lifecycle_endpoints, "invalidate_cache", MagicMock())
    app, _ = make_test_app(itam_lifecycle_endpoints.router)
    return app


def _api_key_token(scopes, role="admin", tenant_id="tenant-a", username="svc-key@tenant-a"):
    return TokenData(username=username, role=role, tenant_id=tenant_id, scopes=scopes, auth_source="api_key")


def _api_key_dependency_override(expected_key, token):
    """Dependency override standing in for the real X-API-Key header path
    (real header parsing + bcrypt lookup already covered end-to-end by
    test_api_key_auth.py) — the client still sends a literal X-API-Key
    header and only a matching value resolves to `token`, so this exercises
    the "key in the header" contract exactly as the real dependency would,
    without re-seeding APIKeyService's own DB-backed validation path."""
    async def _dep(x_api_key: str = Header(default=None, alias="X-API-Key")):
        if x_api_key != expected_key:
            raise HTTPException(status_code=401, detail="Invalid or expired API Key")
        return token
    return _dep


def deployable_asset(**overrides):
    doc = {"id": "asset-1", "tenantId": "tenant-a", "lifecycleStatus": "deployable", "name": "Laptop X1"}
    doc.update(overrides)
    return doc


@pytest.fixture
def patch_rbac_utils_db(monkeypatch):
    """verify_permission (rbac_utils) calls the real database.get_database()
    directly rather than through the router's own db handle — patch it here
    so the DB-role lookup misses and falls through to DEFAULT_PERMISSIONS
    (role "admin" already grants manage:assets there), letting Task 2's
    excluded-surface / catalog-narrowing tests exercise the real
    verify_permission + _scopes_allow enforcement chain end to end."""
    stub_db = MagicMock()
    stub_db.roles = _make_col(find_one=AsyncMock(return_value=None))
    monkeypatch.setattr("rbac_utils.get_database", lambda: stub_db)
    return stub_db


def _session_admin_token(tenant_id="tenant-a"):
    return make_token_data(tenant_id=tenant_id, role="admin", username="admin@example.com")


def _api_key_only_app(router):
    """App mounting one router with ONLY get_current_user_or_api_key overridden
    (to an api_key-sourced TokenData) — get_current_user itself is left
    entirely un-overridden, so a route still gated by plain get_current_user
    hits the real oauth2 dependency and 401s with no Authorization header,
    proving an API key alone cannot reach it."""
    app = FastAPI()
    app.include_router(router)
    api_key_token = TokenData(
        username="svc-key@tenant-a", role="admin", tenant_id="tenant-a",
        scopes=["manage:assets", "manage:itam", "admin:itam"], auth_source="api_key",
    )
    app.dependency_overrides[get_current_user_or_api_key] = lambda: api_key_token
    return app


def _session_app(router, current_user=None):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: current_user or _session_admin_token()
    return app


def _minimal_asset_db():
    db = MagicMock()
    for name in ("assets", "manufacturers", "asset_models", "counters"):
        setattr(db, name, _make_col())
    db.assets.find_one = AsyncMock(return_value=None)  # no duplicate assetTag
    db.assets.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock-id"))
    return db


def _catalog_list_db():
    db = MagicMock()
    db.manufacturers = MagicMock()
    db.manufacturers.find = MagicMock(return_value=_chainable_cursor([]))
    db.__getitem__ = MagicMock(side_effect=lambda name: getattr(db, name))
    return db


def _build_route_case(monkeypatch, which):
    """One representative route per _require_itam_admin-gated router family
    (73-VALIDATION.md: asset / lifecycle / catalog / reporting). Returns
    (app, method, path, kwargs)."""
    monkeypatch.setattr(itam_asset_endpoints, "verify_permission", AsyncMock(return_value=True))
    monkeypatch.setattr(itam_catalog_endpoints, "verify_permission", AsyncMock(return_value=True))

    if which == "asset":
        db = _minimal_asset_db()
        monkeypatch.setattr(itam_asset_endpoints, "get_database", lambda: db)
        monkeypatch.setattr(itam_asset_endpoints, "invalidate_cache", MagicMock())
        monkeypatch.setattr(itam_asset_endpoints, "log_itam_action", AsyncMock())
        app = FastAPI()
        app.include_router(itam_asset_endpoints.router)
        return app, "post", "/api/assets", {"json": {"name": "Laptop", "assetTag": "MANUAL-1"}}

    if which == "lifecycle":
        db = MagicMock()
        for name in ("assets", "users", "locations", "assignment_history"):
            setattr(db, name, _make_col())
        db.assets.find_one_and_update = AsyncMock(return_value=deployable_asset())
        db.users.find_one = AsyncMock(return_value={"id": "user-7"})
        db.assignment_history.insert_one = AsyncMock(return_value=MagicMock(inserted_id="hist-y"))
        monkeypatch.setattr(
            itam_lifecycle_endpoints, "get_database",
            lambda: MockTenantIsolatedDatabase(db, "tenant-a"),
        )
        monkeypatch.setattr(itam_lifecycle_endpoints, "invalidate_cache", MagicMock())
        app = FastAPI()
        app.include_router(itam_lifecycle_endpoints.router)
        return app, "post", "/api/assets/asset-1/checkout", {"json": {"targetType": "user", "targetId": "user-7"}}

    if which == "catalog":
        db = _catalog_list_db()
        monkeypatch.setattr(itam_catalog_endpoints, "get_database", lambda: db)
        app = FastAPI()
        app.include_router(itam_catalog_endpoints.router)
        return app, "get", "/api/itam/catalog/manufacturers", {}

    if which == "reporting":
        app = FastAPI()
        app.include_router(itam_reporting_endpoints.router)
        return app, "get", "/api/itam/reports", {}

    raise ValueError(which)  # pragma: no cover
