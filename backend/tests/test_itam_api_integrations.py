"""ITAM-API-01 auth-spine regression suite (Phase 73 Plan 01).

Task 1 — the tracer: an API-key-authenticated caller checks an asset out
over HTTP, the call is narrowed by the key's scopes, and the checkout fires
`asset.checked_out` without blocking the response. Tasks 2/3 extend this
same module with the excluded-surfaces, session-parity, scope-narrowing and
rate-limit regressions (selectable via `-k excluded_surfaces`,
`-k catalog_scope_narrowing`, `-k session_auth`, `-k scoped_key_allowed`,
`-k scope_narrowing_enforced`, `-k rate_limit`).

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
from fastapi import Header, HTTPException
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.conftest import make_test_app, make_token_data, _make_col

from auth_types import TokenData
from api_key_auth import get_current_user_or_api_key
from itam_webhook_events import EVENT_ASSET_CHECKED_OUT
import itam_lifecycle_endpoints
import itam_asset_endpoints

FAKE_API_KEY = "test-omni-pat-fixture-key"


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
