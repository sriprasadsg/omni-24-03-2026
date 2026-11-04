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


def test_signup_waits_for_approval_without_a_session(monkeypatch):
    """Approval-gated sign-up (2026-10-20): the tenant and its admin are stored as pending, the
    response carries no token or permissions, and no refresh cookie is set."""
    db, raw = role_store(users=[], roles=shared_role_docs(), tenants=[], user_consents=[])
    client = make_auth_client(db, monkeypatch)
    resp = client.post("/api/auth/signup", json=SIGNUP_BODY)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["pending"] is True and "access_token" not in body and "user" not in body
    assert "omni_refresh" not in resp.headers.get("set-cookie", "")
    stored = [u for u in raw.users.docs if u["email"] == SIGNUP_BODY["email"]]
    assert len(stored) == 1 and stored[0]["status"] == "Pending" and "permissions" not in stored[0]
    tenant = next(t for t in raw.tenants.docs if t["id"] == body["tenant"]["id"])
    assert tenant["status"] == "pending_approval"
    assert tenant["enabledFeatures"] == ["view:dashboard", "view:profile", "screen:dashboard"]


def test_signup_with_a_taken_company_name_is_refused_not_a_500(monkeypatch):
    """2026-11-03: a Super Admin had already added "shieldforgetech"; signing up with the same
    company name hit the unique tenants.name index and surfaced as a bare 500."""
    db, raw = role_store(users=[], roles=shared_role_docs(),
                         tenants=[{"id": "tenant_taken", "name": SIGNUP_BODY["companyName"]}], user_consents=[])
    client = make_auth_client(db, monkeypatch)
    resp = client.post("/api/auth/signup", json=SIGNUP_BODY)
    assert resp.status_code == 400, resp.text
    assert "company name is already registered" in resp.json()["detail"]
    assert [t["id"] for t in raw.tenants.docs] == ["tenant_taken"]
    assert raw.users.docs == [] and raw.user_consents.docs == []


def test_a_concurrent_signup_for_the_same_company_name_is_refused(monkeypatch):
    """The pre-check can lose a race; the unique index's duplicate-key error still becomes a 400."""
    from pymongo.errors import DuplicateKeyError

    class _RacingTenants(StoreCollection):
        async def insert_one(self, doc, **k):
            raise DuplicateKeyError("E11000 duplicate key error collection: omni_platform.tenants index: name_1")

    db, raw = role_store(users=[], roles=shared_role_docs(), tenants=_RacingTenants([]), user_consents=[])
    client = make_auth_client(db, monkeypatch)
    resp = client.post("/api/auth/signup", json=SIGNUP_BODY)
    assert resp.status_code == 400, resp.text
    assert "company name is already registered" in resp.json()["detail"]
    assert raw.users.docs == []


def test_a_pending_signup_cannot_sign_in_and_is_told_why(monkeypatch):
    db, raw = role_store(users=[], roles=shared_role_docs(), tenants=[], user_consents=[])
    client = make_auth_client(db, monkeypatch)
    assert client.post("/api/auth/signup", json=SIGNUP_BODY).status_code == 200
    resp = client.post("/api/auth/login", json={"email": SIGNUP_BODY["email"], "password": SIGNUP_BODY["password"]})
    assert resp.status_code == 403
    assert "waiting for approval" in resp.json()["detail"]


# ── 87 WR-04: invites store the address lower-cased, so sign-in ignores the case typed ──

def _invited(email):
    user = make_user(email, "viewer", "t1")
    user.pop("username")  # an invited person has no username, only the stored address
    return user


def test_an_invited_address_signs_in_whatever_case_is_typed(monkeypatch):
    """protects=an invitee signs in typing their mailbox's own capitals; fails_when=login matches the
    lower-cased stored address case-sensitively; no_claim=usernames, which still match exactly."""
    client = _client(monkeypatch, shared_role_docs(), _invited("jane.doe@corp.test"))
    assert login(client, "Jane.Doe@Corp.TEST").status_code == 200
    assert login(client, " jane.doe@corp.test ").status_code == 200


def test_an_address_stored_as_typed_still_signs_in_as_before(monkeypatch):
    client = _client(monkeypatch, shared_role_docs(), _invited("Legacy.User@Corp.test"))
    assert login(client, "Legacy.User@Corp.test").status_code == 200


def test_case_variants_of_an_address_share_one_lockout(monkeypatch):
    """protects=the five-attempt lock-out; fails_when=each capitalization gets its own failure counter."""
    client = _client(monkeypatch, shared_role_docs(), _invited("jane.doe@corp.test"))
    for typed in ("Jane.Doe@corp.test", "JANE.DOE@corp.test", "jane.Doe@corp.test",
                  "Jane.DOE@corp.test", "jane.doe@CORP.test"):
        assert login(client, typed, password="Wrong1!pass").status_code == 401
    assert login(client, "jane.doe@corp.test").status_code == 429


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
