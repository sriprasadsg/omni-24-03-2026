"""
Production hardening (CSO findings 92a814a0 and 684a3b71).

- app_env: one environment variable, unset = production (fail closed).
- Socket.IO in production accepts the same origins as the REST API instead
  of localhost only (or "*" in development).
- Migration 009 seals plaintext cloud integration secrets.
- Active-response mutations need manage:active_response; admins hold it.
Hermetic — no Mongo.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app_env
from auth_types import TokenData
from authentication_service import get_current_user
from rbac_service import rbac_service


@pytest.fixture(autouse=True)
def _restore_tenant_context():
    """verify_token/get_current_user set the ambient tenant context; restore it
    so later tests that assert an empty context are unaffected."""
    from tenant_context import _tenant_id_ctx
    token = _tenant_id_ctx.set(_tenant_id_ctx.get())
    yield
    _tenant_id_ctx.reset(token)


# ── app_env ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("env,app_env_var,expected", [
    (None, None, True),               # unset → production
    ("production", None, True),
    ("staging", None, True),
    ("development", None, False),
    ("test", None, False),
    (None, "development", False),     # legacy APP_ENV alias
    ("production", "development", True),  # ENVIRONMENT wins
])
def test_is_production(monkeypatch, env, app_env_var, expected):
    for name, value in (("ENVIRONMENT", env), ("APP_ENV", app_env_var)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    assert app_env.is_production() is expected


# ── Socket.IO origins ────────────────────────────────────────────────────────

def test_socketio_production_allows_listed_and_same_host_only(monkeypatch):
    import websocket_manager
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("SOCKETIO_CORS_ORIGINS", raising=False)
    monkeypatch.setenv("CORS_ORIGINS", "https://omni.example.com")
    check = websocket_manager._build_socketio_cors()
    assert check("https://omni.example.com", {"HTTP_HOST": "10.0.0.4:5000"})
    # Behind nginx (Host forwarded, scheme not): the page's own host is allowed.
    assert check("https://20.1.2.3", {"HTTP_HOST": "20.1.2.3"})
    assert check("https://omni.corp", {"HTTP_HOST": "backend:5000", "HTTP_X_FORWARDED_HOST": "omni.corp"})
    # A cross-site page is not.
    assert not check("https://evil.example", {"HTTP_HOST": "20.1.2.3"})
    assert not check("https://evil.example", {})


def test_socketio_development_stays_permissive(monkeypatch):
    import websocket_manager
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("SOCKETIO_CORS_ORIGINS", raising=False)
    assert websocket_manager._build_socketio_cors() == "*"


# ── Migration 009 ────────────────────────────────────────────────────────────

async def test_migration_009_seals_plaintext_secrets(monkeypatch):
    import importlib
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("INTEGRATION_ENCRYPTION_KEY", key)
    mig = importlib.import_module("migrations.009_encrypt_cloud_integration_secrets")

    docs = [
        {"_id": 1, "config": {"client_secret": "plain", "tenant": "t"}},
        {"_id": 2, "config": {"client_secret": "enc:already"}},
    ]

    class Cursor:
        def __init__(self, items): self.items = iter(items)
        def __aiter__(self): return self
        async def __anext__(self):
            try:
                return next(self.items)
            except StopIteration:
                raise StopAsyncIteration

    db = MagicMock()
    db.cloud_integrations.find = MagicMock(return_value=Cursor(docs))
    db.cloud_integrations.update_one = AsyncMock()
    await mig.up(db)

    db.cloud_integrations.update_one.assert_awaited_once()
    (flt, update), _ = db.cloud_integrations.update_one.call_args
    assert flt == {"_id": 1}
    sealed = update["$set"]["config"]["client_secret"]
    assert sealed.startswith("enc:")
    assert Fernet(key.encode()).decrypt(sealed[4:].encode()) == b"plain"


# ── Active response ──────────────────────────────────────────────────────────

def _client(role, permissions, agent_doc=None):
    import active_response_endpoints as ar
    app = FastAPI()
    app.include_router(ar.router)
    app.dependency_overrides[get_current_user] = lambda: TokenData(
        username="u@example.com", role=role, tenant_id="tenant-a", mfa_verified=True)
    db = MagicMock()
    db.agents.find_one = AsyncMock(return_value=agent_doc)
    return app, [patch.object(rbac_service, "get_user_permissions", new=AsyncMock(return_value=permissions)),
                 patch.object(ar, "get_database", return_value=db)]


@pytest.mark.parametrize("method,path,body", [
    ("post", "/api/active-response/execute", {"agent_id": "a1", "action": "isolate_agent"}),
    ("post", "/api/active-response/rules", {}),
    ("put", "/api/active-response/rules/r1", {}),
    ("delete", "/api/active-response/rules/r1", None),
])
def test_viewer_cannot_mutate_active_response(method, path, body):
    app, patches = _client("viewer", ["view:dashboard"])
    with patches[0], patches[1], TestClient(app) as client:
        resp = getattr(client, method)(path, json=body) if body is not None else getattr(client, method)(path)
    assert resp.status_code == 403, resp.text


def test_permitted_user_passes_authorization():
    app, patches = _client("admin", ["manage:active_response"], agent_doc=None)
    with patches[0], patches[1], TestClient(app) as client:
        resp = client.post("/api/active-response/execute", json={"agent_id": "a1", "action": "isolate_agent"})
    assert resp.status_code == 404  # past the permission gate; agent not found


def test_admin_roles_hold_active_response_permission():
    for role in ("admin", "Tenant Admin"):
        assert "manage:active_response" in rbac_service.default_roles[role]
    assert "manage:active_response" not in rbac_service.default_roles["viewer"]
