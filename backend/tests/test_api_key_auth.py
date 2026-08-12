"""
Tests for api_key_auth.py and the X-API-Key path on webhook_endpoints.py.

Covers:
  - generate_api_key stores keyHash = SHA-256(plaintext) (hash-at-rest, T-33-KEY)
  - get_current_user_or_api_key: valid key → tenant-scoped api-integration identity,
    wrong/revoked/absent credentials → 401, JWT path delegates unchanged
  - api-integration is provably not a super role (T-33-ROLE)
  - the four connector webhook routes accept the API-key path and stay tenant-scoped
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import hashlib
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from authentication_service import get_current_user
from auth_types import TokenData
import auth_roles
import api_key_auth
from api_key_auth import get_current_user_or_api_key


# ─── helpers (cloned from test_automation_and_baa.py) ────────────────────────

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


def _app(router, user, dependency=get_current_user):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[dependency] = lambda: user
    return app


# ─── Task 1: hash-at-rest (generate_api_key writes keyHash) ──────────────────

def test_hash_verify_generate_api_key_stores_sha256_keyhash():
    import tenant_endpoints

    tenants = _col(find_one=AsyncMock(return_value={"id": "t1", "name": "Tenant One"}))
    mock_mongodb = MagicMock()
    mock_mongodb.db = _db(tenants=tenants)

    with patch.object(tenant_endpoints, "mongodb", mock_mongodb):
        app = _app(tenant_endpoints.router, _user(role="Super Admin", tenant_id="t1"))
        client = TestClient(app)
        res = client.post("/api/tenants/t1/api-keys", json={"name": "n8n"})

    assert res.status_code == 200
    plaintext = res.json()["key"]
    assert plaintext.startswith("omni_sk_")

    pushed = tenants.update_one.call_args[0][1]["$push"]["apiKeys"]
    assert pushed["keyHash"] == hashlib.sha256(plaintext.encode()).hexdigest()
    # display prefix unchanged, plaintext never persisted
    assert pushed["key"].startswith(plaintext[:12])
    assert pushed["key"] != plaintext


# ─── Task 1: get_current_user_or_api_key dependency ──────────────────────────

@pytest.mark.asyncio
async def test_dependency_valid_key_returns_tenant_scoped_api_integration():
    key = "omni_sk_valid"
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    tenants = _col(find_one=AsyncMock(return_value={"id": "t1", "apiKeys": [{"keyHash": key_hash}]}))
    # ITAM-USR-05 (64-05): get_current_user_or_api_key now tries the new
    # user-scoped token path (db.users) first; a legacy tenant-scoped key
    # like this one has no matching user-scoped record, so db.users.find_one
    # must resolve to None (not an unconfigured MagicMock) for the fallback
    # to the tenant-scoped lookup below to run.
    mock_mongodb = MagicMock()
    mock_mongodb.db = _db(tenants=tenants, users=_col())

    with patch.object(api_key_auth, "mongodb", mock_mongodb), \
         patch.object(api_key_auth, "set_tenant_id") as set_tid:
        user = await get_current_user_or_api_key(api_key=key, token=None)

    assert user.role == "api-integration"
    assert user.tenant_id == "t1"
    assert user.username == "api-key"
    set_tid.assert_called_once_with("t1")
    # lookup is by hash equality, never plaintext
    assert tenants.find_one.call_args[0][0] == {"apiKeys.keyHash": key_hash}


@pytest.mark.asyncio
async def test_dependency_wrong_key_401():
    tenants = _col(find_one=AsyncMock(return_value=None))
    mock_mongodb = MagicMock()
    mock_mongodb.db = _db(tenants=tenants, users=_col())

    with patch.object(api_key_auth, "mongodb", mock_mongodb):
        with pytest.raises(HTTPException) as exc:
            await get_current_user_or_api_key(api_key="omni_sk_wrong", token=None)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_dependency_revoked_key_401():
    key = "omni_sk_revoked"
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    tenants = _col(find_one=AsyncMock(return_value={
        "id": "t1", "apiKeys": [{"keyHash": key_hash, "revoked": True}]
    }))
    mock_mongodb = MagicMock()
    mock_mongodb.db = _db(tenants=tenants, users=_col())

    with patch.object(api_key_auth, "mongodb", mock_mongodb):
        with pytest.raises(HTTPException) as exc:
            await get_current_user_or_api_key(api_key=key, token=None)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_dependency_no_credentials_401():
    with pytest.raises(HTTPException) as exc:
        await get_current_user_or_api_key(api_key=None, token=None)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_dependency_jwt_path_delegates_to_verify_token():
    jwt_user = _user(role="admin", tenant_id="t9")
    with patch.object(api_key_auth, "verify_token_async", AsyncMock(return_value=jwt_user)) as vta:
        user = await get_current_user_or_api_key(api_key=None, token="a.jwt.token")
    assert user is jwt_user
    vta.assert_awaited_once_with("a.jwt.token")


def test_dependency_api_integration_role_is_not_super():
    assert "api-integration" not in auth_roles.SUPER_ROLES
    assert "api-integration" not in auth_roles.SUPER_AND_ADMIN_ROLES


# ─── Task 2: webhook routes accept the API-key path, tenant-scoped ───────────

def _webhook_app():
    import webhook_endpoints
    app = FastAPI()
    app.include_router(webhook_endpoints.router)
    app.dependency_overrides[get_current_user_or_api_key] = \
        lambda: _user(role="api-integration", tenant_id="t1")
    return app, webhook_endpoints


def test_webhook_route_list_is_tenant_scoped_for_api_integration():
    webhooks = _col()
    db = _db(webhooks=webhooks)
    app, mod = _webhook_app()
    with patch.object(mod, "get_database", return_value=db):
        client = TestClient(app)
        res = client.get("/api/webhooks")

    assert res.status_code == 200
    query = webhooks.find.call_args[0][0]
    assert query == {"tenantId": "t1"}  # never the unrestricted {} super-role query


def test_webhook_route_create_accepts_api_key_identity():
    webhooks = _col()
    db = _db(webhooks=webhooks)
    app, mod = _webhook_app()
    with patch.object(mod, "get_database", return_value=db), \
         patch.object(mod, "_is_safe_webhook_url", return_value=True):
        client = TestClient(app)
        res = client.post("/api/webhooks", json={
            "name": "n8n hook", "url": "https://example.com/hook", "events": ["grc.event"]
        })

    assert res.status_code == 200
    inserted = webhooks.insert_one.call_args[0][0]
    assert inserted["tenantId"] == "t1"
    assert inserted["createdBy"] == "test@example.com"


def test_webhook_route_delete_is_tenant_scoped():
    webhooks = _col(delete_one=AsyncMock(return_value=MagicMock(deleted_count=1)))
    db = _db(webhooks=webhooks)
    app, mod = _webhook_app()
    with patch.object(mod, "get_database", return_value=db):
        client = TestClient(app)
        res = client.delete("/api/webhooks/wh-123")

    assert res.status_code == 200
    assert webhooks.delete_one.call_args[0][0] == {"id": "wh-123", "tenantId": "t1"}


def test_webhook_route_deliveries_is_tenant_scoped():
    webhooks = _col(find_one=AsyncMock(return_value={"_id": 1}))
    deliveries = _col()
    deliveries.find.return_value.sort.return_value.limit = MagicMock(
        return_value=MagicMock(to_list=AsyncMock(return_value=[]))
    )
    db = _db(webhooks=webhooks, webhook_deliveries=deliveries)
    app, mod = _webhook_app()
    with patch.object(mod, "get_database", return_value=db):
        client = TestClient(app)
        res = client.get("/api/webhooks/wh-123/deliveries")

    assert res.status_code == 200
    assert webhooks.find_one.call_args[0][0] == {"id": "wh-123", "tenantId": "t1"}


def test_webhook_route_update_still_requires_jwt_user():
    """update_webhook stays on get_current_user — the api-key override must not apply."""
    app, _mod = _webhook_app()
    client = TestClient(app)
    res = client.put("/api/webhooks/wh-123", json={"status": "Paused"})
    assert res.status_code == 401  # no JWT supplied; API-key override does not cover this route
