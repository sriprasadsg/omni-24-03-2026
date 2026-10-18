"""SC1/SC2 (ACC-01): /login and /me deliver the same server-evaluated permission list.

Both endpoints call rbac_service.session_permissions -> effective_permissions.
/login is a public path (no tenant ContextVar), so these tests run it without
tenant context to prove tenant-scoped role documents are still visible (D-23).
"""
import logging

import pytest

import rbac_defaults
from tests.rbac_test_support import (
    StoreCollection,
    login,
    make_auth_client,
    make_user,
    me,
    reset_shared_limiter,
    role_store,
    shared_role_docs,
)


@pytest.fixture(autouse=True)
def _reset_limiter():
    reset_shared_limiter()
    yield
    reset_shared_limiter()


def _client(monkeypatch, roles, *users):
    db, _raw = role_store(users=list(users), roles=roles)
    return make_auth_client(db, monkeypatch)


def _both(client, user):
    first = login(client, user["email"])
    assert first.status_code == 200, first.text
    second = me(client, user["email"], user["role"], user["tenantId"])
    assert second.status_code == 200, second.text
    return first.json()["user"]["permissions"], second.json()["permissions"]


ITAM_EXPECTED = {
    # D-11 (Phase 77): the 8 table defaults followed by the manage:X => view:X/request:X closure.
    "itam_admin": ["manage:assets", "manage:finance", "manage:itam", "manage:licenses",
                   "manage:procurement", "manage:users", "view:itam", "view:profile",
                   "request:assets", "view:assets", "view:licenses"],
    "itam_user": ["request:assets", "view:assets", "view:itam", "view:licenses", "view:profile"],
    "itam_viewer": ["view:assets", "view:itam", "view:licenses", "view:profile"],
}


@pytest.mark.parametrize("role", ["itam_admin", "itam_user", "itam_viewer"])
def test_itam_role_gets_real_permissions_from_login_and_me(monkeypatch, role):
    user = make_user(f"{role}@acme.test", role, "t1")
    client = _client(monkeypatch, shared_role_docs(), user)
    logged_in, current = _both(client, user)
    assert logged_in == ITAM_EXPECTED[role]
    assert current == logged_in
    assert "view:profile" in logged_in
    # D-11: itam_admin now also receives view:assets through the manage:assets closure
    assert "view:assets" in logged_in
    assert ("manage:assets" in logged_in) == (role == "itam_admin")
    assert "view:dashboard" not in logged_in


def test_itam_viewer_login_list_is_exact(monkeypatch):
    user = make_user("viewer-itam@acme.test", "itam_viewer", "t1")
    client = _client(monkeypatch, [], user)
    resp = login(client, user["email"])
    assert resp.status_code == 200
    assert resp.json()["user"]["permissions"] == ["view:assets", "view:itam", "view:licenses", "view:profile"]


PARITY_ROLES = ["Tenant Admin", "admin", "Admin", "tenant_admin", "user", "analyst", "security_analyst",
                "incident_responder", "viewer", "itam_admin", "itam_user", "itam_viewer"]


@pytest.mark.parametrize("seeded", [True, False], ids=["seed-docs", "no-docs"])
@pytest.mark.parametrize("role", PARITY_ROLES)
def test_login_equals_me_for_every_builtin_role(monkeypatch, role, seeded):
    user = make_user("parity@acme.test", role, "t1")
    client = _client(monkeypatch, shared_role_docs() if seeded else [], user)
    logged_in, current = _both(client, user)
    key = rbac_defaults.canonical_key(role.lower().replace(" ", "_"))
    assert logged_in, f"{role} logged in with an empty permission list"
    assert logged_in == current
    # D-11 (Phase 77): the delivered list is the table plus the closure; only itam_admin gains anything.
    expected = ITAM_EXPECTED[key] if key == "itam_admin" else list(rbac_defaults.defaults_for(key))
    assert logged_in == expected


def test_tenant_scoped_document_extends_both_endpoints_for_own_tenant_only(monkeypatch):
    roles = shared_role_docs() + [{"name": "viewer", "tenantId": "t1", "permissions": ["view:custom_extra"]}]
    t1_user = make_user("v1@acme.test", "viewer", "t1")
    t2_user = make_user("v2@other.test", "viewer", "t2")
    client = _client(monkeypatch, roles, t1_user, t2_user)
    t1_login, t1_me = _both(client, t1_user)
    assert t1_login == t1_me
    assert t1_login[-1] == "view:custom_extra"
    assert t1_login[:-1] == list(rbac_defaults.defaults_for("viewer"))
    t2_login, t2_me = _both(client, t2_user)
    assert "view:custom_extra" not in t2_login and "view:custom_extra" not in t2_me
    assert t2_login == t2_me


@pytest.mark.parametrize("role", ["Super Admin", "super_admin", "superadmin", "platform-admin"])
def test_super_admin_variants_get_wildcard(monkeypatch, role):
    user = make_user("root@platform.test", role, "platform")
    client = _client(monkeypatch, shared_role_docs(), user)
    logged_in, current = _both(client, user)
    assert logged_in == ["*"]
    assert current == ["*"]


def test_role_without_permissions_still_logs_in_and_warns(monkeypatch, caplog):
    user = make_user("legacy@acme.test", "legacy_custom_role", "t1")
    client = _client(monkeypatch, shared_role_docs(), user)
    with caplog.at_level(logging.WARNING):
        resp = login(client, user["email"])
    assert resp.status_code == 200
    assert resp.json()["user"]["permissions"] == []
    assert any(r.levelno == logging.WARNING and "legacy_custom_role" in r.getMessage() for r in caplog.records)


def test_stored_per_user_permissions_are_ignored(monkeypatch):
    user = make_user("stored@acme.test", "viewer", "t1", permissions=["bogus:perm"])
    client = _client(monkeypatch, shared_role_docs(), user)
    logged_in, current = _both(client, user)
    assert "bogus:perm" not in logged_in and "bogus:perm" not in current
    assert logged_in == current == list(rbac_defaults.defaults_for("viewer"))


class _RaisingRoles(StoreCollection):
    async def find_one(self, flt=None, projection=None, **k):
        raise RuntimeError("role store down")


def test_role_store_outage_degrades_to_defaults_on_login(monkeypatch):
    user = make_user("outage@acme.test", "viewer", "t1")
    db, _raw = role_store(users=[user], roles=_RaisingRoles())
    client = make_auth_client(db, monkeypatch)
    resp = login(client, user["email"])
    assert resp.status_code == 200
    assert resp.json()["user"]["permissions"] == list(rbac_defaults.defaults_for("viewer"))


# ── Signup and MFA verify-login deliver the same resolver list (D-24, D-07) ──

SIGNUP_BODY = {"companyName": "Acme Corp", "name": "Ada Admin",
               "email": "ada@acme-signup.test", "password": "Str0ng!Passw0rd#42"}


def test_signup_response_carries_resolver_permissions(monkeypatch):
    db, raw = role_store(users=[], roles=shared_role_docs(), tenants=[], user_consents=[])
    client = make_auth_client(db, monkeypatch)
    resp = client.post("/api/auth/signup", json=SIGNUP_BODY)
    assert resp.status_code == 200, resp.text
    perms = resp.json()["user"]["permissions"]
    assert perms == list(rbac_defaults.defaults_for("tenant_admin"))
    assert "manage:users" in perms and "manage:tenants" not in perms
    stored = [u for u in raw.users.docs if u["email"] == SIGNUP_BODY["email"]]
    assert len(stored) == 1
    assert "permissions" not in stored[0]


def test_signup_permissions_match_me(monkeypatch):
    db, raw = role_store(users=[], roles=shared_role_docs(), tenants=[], user_consents=[])
    client = make_auth_client(db, monkeypatch)
    resp = client.post("/api/auth/signup", json=SIGNUP_BODY)
    assert resp.status_code == 200, resp.text
    tenant_id = resp.json()["tenant"]["id"]
    current = me(client, SIGNUP_BODY["email"], "Tenant Admin", tenant_id)
    assert current.status_code == 200, current.text
    assert current.json()["permissions"] == resp.json()["user"]["permissions"]


def _mfa_client(monkeypatch, db, email):
    from unittest.mock import AsyncMock
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware
    from slowapi.util import get_remote_address
    import mfa_endpoints
    import mfa_service

    monkeypatch.setattr(mfa_endpoints, "get_database", lambda: db)
    monkeypatch.setattr(mfa_service, "verify_mfa_token",
                        AsyncMock(return_value={"success": True, "email": email}))
    app = FastAPI()
    app.state.limiter = Limiter(key_func=get_remote_address)
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.include_router(mfa_endpoints.router)
    return TestClient(app)


def _mfa_verify(client):
    return client.post("/api/mfa/verify", json={"session_token": "s" * 32, "code": "123456"})


def test_mfa_verify_carries_resolver_permissions(monkeypatch):
    user = make_user("itam.mfa@acme.test", "itam_user", "t1")
    db, _raw = role_store(users=[user], roles=shared_role_docs())
    client = _mfa_client(monkeypatch, db, user["email"])
    resp = _mfa_verify(client)
    assert resp.status_code == 200, resp.text
    assert resp.json()["user"]["permissions"] == [
        "request:assets", "view:assets", "view:itam", "view:licenses", "view:profile"]


def test_mfa_verify_ignores_stored_permissions(monkeypatch):
    user = make_user("stale.mfa@acme.test", "viewer", "t1", permissions=["bogus:perm"])
    db, _raw = role_store(users=[user], roles=shared_role_docs())
    client = _mfa_client(monkeypatch, db, user["email"])
    resp = _mfa_verify(client)
    assert resp.status_code == 200, resp.text
    perms = resp.json()["user"]["permissions"]
    assert "bogus:perm" not in perms
    assert perms == list(rbac_defaults.defaults_for("viewer"))
