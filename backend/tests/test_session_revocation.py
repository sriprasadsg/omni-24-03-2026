"""
Sessions end when the account changes under them.

Disabling, deleting, re-roling or re-passwording a user records a per-user
cutoff (authentication_service.revoke_user_sessions); every access or refresh
token issued before it is rejected. Disabled accounts also can't start a new
session on any login path, and directory sign-ins (LDAP/SAML) no longer
re-enable an account an admin disabled.

The revocation tests run against the per-run test database (conftest pins
MONGODB_DB_NAME to omni_test_<pid>) because the $or/$max query semantics are
the thing under test; they skip when no local Mongo is reachable. The
endpoint wiring tests are hermetic.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as _jwt
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import authentication_service as auth_svc
from auth_types import TokenData

ALICE = "alice@revocation.test"
BOB = "bob@revocation.test"


@pytest.fixture(autouse=True)
def _clean_caches():
    auth_svc._user_cutoff_cache.clear()
    auth_svc._revoked_jti_cache.clear()
    auth_svc._revocation_cache_last_sync = 0.0
    yield
    auth_svc._user_cutoff_cache.clear()
    auth_svc._revoked_jti_cache.clear()


class _Shim:
    """Matches the db._db access pattern the auth code uses."""

    def __init__(self, mdb):
        self._db = mdb


@pytest.fixture
async def live_db():
    import motor.motor_asyncio
    uri = os.environ.get("MONGODB_URL") or os.environ.get("MONGO_URI") or "mongodb://localhost:27017"
    client = motor.motor_asyncio.AsyncIOMotorClient(uri, serverSelectionTimeoutMS=1500)
    try:
        await client.admin.command("ping")
    except Exception:
        client.close()
        pytest.skip(f"No MongoDB reachable at {uri}")
    mdb = client[os.environ["MONGODB_DB_NAME"]]
    await mdb.revoked_tokens.create_index("jti", unique=True)
    await mdb.revoked_tokens.delete_many({})
    await mdb.users.delete_many({"email": {"$in": [ALICE, BOB]}})
    shim = _Shim(mdb)
    with patch("database.get_database", return_value=shim):
        yield shim
    await mdb.revoked_tokens.delete_many({})
    await mdb.users.delete_many({"email": {"$in": [ALICE, BOB]}})
    client.close()


def _access(email, role="Viewer"):
    return auth_svc.create_access_token({"sub": email, "role": role, "tenant_id": "t1"})


async def _rejected(token) -> bool:
    try:
        await auth_svc.verify_token_async(token)
    except HTTPException as exc:
        assert exc.status_code == 401
        return True
    return False


# --- revocation itself (live Mongo) -----------------------------------------

async def test_revocation_rejects_tokens_issued_before_it(live_db):
    old = _access(ALICE)
    assert not await _rejected(old)
    await auth_svc.revoke_user_sessions(ALICE, "test")
    auth_svc._user_cutoff_cache.clear()  # prove the DB lookup alone rejects it
    assert await _rejected(old)
    with pytest.raises(HTTPException):  # and the sync path, from the cache the DB hit filled
        auth_svc.verify_token(old)


async def test_tokens_issued_after_revocation_work(live_db):
    await auth_svc.revoke_user_sessions(ALICE, "test")
    fresh = _access(ALICE)
    assert not await _rejected(fresh)
    assert auth_svc.verify_token(fresh).username == ALICE


async def test_revocation_is_per_user(live_db):
    bobs = _access(BOB)
    await auth_svc.revoke_user_sessions(ALICE, "test")
    assert not await _rejected(bobs)


async def test_legacy_token_without_iat_is_revoked(live_db):
    # Tokens minted before iat was added count as issued at time zero.
    from datetime import datetime, timedelta, timezone
    legacy = _jwt.encode(
        {"sub": ALICE, "role": "Viewer", "tenant_id": "t1", "jti": "legacy-1",
         "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        auth_svc.SECRET_KEY, algorithm=auth_svc.ALGORITHM,
    )
    assert not await _rejected(legacy)
    await auth_svc.revoke_user_sessions(ALICE, "test")
    assert await _rejected(legacy)


async def test_other_workers_learn_cutoffs_from_the_bulk_sync(live_db):
    old = _access(ALICE)
    await auth_svc.revoke_user_sessions(ALICE, "test")
    auth_svc._user_cutoff_cache.clear()  # a worker that never saw the revoke
    auth_svc.verify_token(old)  # sync path has nothing cached yet
    assert not await _rejected(_access(BOB))  # any async verify runs the 60 s bulk sync
    with pytest.raises(HTTPException):
        auth_svc.verify_token(old)


async def test_cutoff_doc_outlives_refresh_tokens(live_db):
    from datetime import datetime, timezone
    await auth_svc.revoke_user_sessions(ALICE.upper(), "test")  # email case doesn't matter
    doc = await live_db._db.revoked_tokens.find_one({"jti": "user-cutoff:" + ALICE})
    assert doc["type"] == "user_cutoff"
    remaining = doc["expiresAt"].replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)
    assert remaining.days >= auth_svc.REFRESH_TOKEN_EXPIRE_DAYS
    assert "revoked_at" not in doc  # revoked_at carries a 1-day TTL index


def _auth_app():
    import authentication_endpoints as auth_ep
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address
    app = FastAPI()
    app.state.limiter = Limiter(key_func=get_remote_address)
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(auth_ep.router)
    return app


async def test_refresh_token_issued_before_cutoff_is_refused(live_db):
    from httpx import ASGITransport, AsyncClient
    await live_db._db.users.insert_one({"email": ALICE, "role": "Viewer", "tenantId": "t1", "status": "Active"})
    old_refresh = auth_svc.create_refresh_token({"sub": ALICE})
    await auth_svc.revoke_user_sessions(ALICE, "role change")
    new_refresh = auth_svc.create_refresh_token({"sub": ALICE})
    with patch("authentication_endpoints.get_database", return_value=live_db):
        async with AsyncClient(transport=ASGITransport(app=_auth_app()), base_url="http://t") as client:
            refused = await client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
            allowed = await client.post("/api/auth/refresh", json={"refresh_token": new_refresh})
    assert refused.status_code == 401
    assert allowed.status_code == 200


# --- account status ---------------------------------------------------------

@pytest.mark.parametrize("doc,active", [
    ({"status": "Active"}, True),
    ({"status": "active"}, True),
    ({"status": "Inactive"}, False),
    ({"status": "Pending"}, False),
    ({"status": "Disabled"}, False),
    ({"email": ALICE}, True),  # legacy doc without a status field
    ({"is_active": False}, False),
    (None, False),
])
def test_account_is_active(doc, active):
    assert auth_svc.account_is_active(doc) is active


def _login_db(user):
    db = MagicMock()
    db._db.users.find_one = AsyncMock(return_value=user)
    db._db.login_attempts.find_one = AsyncMock(return_value=None)
    db._db.login_attempts.delete_one = AsyncMock()
    db._db.roles.find_one = AsyncMock(return_value=None)
    db.roles.find_one = AsyncMock(return_value=None)
    db.login_events.update_one = AsyncMock()
    return db


def _user(**extra):
    from auth_utils import hash_password
    doc = {"_id": "u1", "email": ALICE, "password": hash_password("Password1!"),
           "role": "Viewer", "tenantId": "t1", "mfa": {"enabled": True}}
    doc.update(extra)
    return doc


@pytest.mark.parametrize("extra", [{"status": "Inactive"}, {"is_active": False}])
def test_disabled_account_cannot_log_in(extra):
    db = _login_db(_user(**extra))
    with patch("authentication_endpoints.get_database", return_value=db), \
         patch("mfa_service.create_mfa_session", new_callable=AsyncMock) as mfa_session:
        r = TestClient(_auth_app()).post("/api/auth/login", json={"email": ALICE, "password": "Password1!"})
    assert r.status_code == 403
    mfa_session.assert_not_awaited()  # not even the MFA step starts


def test_wrong_password_on_disabled_account_still_says_invalid_credentials():
    db = _login_db(_user(status="Inactive"))
    db._db.login_attempts.update_one = AsyncMock()
    with patch("authentication_endpoints.get_database", return_value=db):
        r = TestClient(_auth_app()).post("/api/auth/login", json={"email": ALICE, "password": "Wrong1!aaaa"})
    assert r.status_code == 401


# --- user admin wiring ------------------------------------------------------

ADMIN = TokenData(username="admin@revocation.test", role="Tenant Admin", tenant_id="t1", mfa_verified=True)
TARGET_ID = "65f000000000000000000001"


def _users_client(target):
    import user_endpoints as ue
    from itam_asset_endpoints import _require_itam_admin_session_only
    db = MagicMock()
    db.users.find_one = AsyncMock(side_effect=[target, target])
    db.users.update_one = AsyncMock()
    db.users.delete_one = AsyncMock()
    db.audit_logs.insert_one = AsyncMock()
    # The role-assignment ceiling reads role documents through the raw handle.
    db._db.roles.find_one = AsyncMock(return_value=None)
    app = FastAPI()
    app.include_router(ue.router)
    app.dependency_overrides[_require_itam_admin_session_only] = lambda: ADMIN
    # The manifest tag (Phase 76-09, userManagement) sits next to the admin check; ADMIN holds it.
    app.dependency_overrides[ue.USER_MANAGEMENT_GUARD] = lambda: ADMIN
    return TestClient(app), db, ue


def _target(**extra):
    from bson import ObjectId
    doc = {"_id": ObjectId(TARGET_ID), "email": ALICE, "role": "Viewer", "tenantId": "t1",
           "status": "Active", "full_name": "Alice"}
    doc.update(extra)
    return doc


@pytest.mark.parametrize("body,reason", [
    ({"role": "Tenant Admin"}, "role"),
    ({"status": "inactive"}, "status"),
    ({"password": "N3w-Passw0rd!xyz"}, "password"),
])
def test_user_update_revokes_sessions(body, reason):
    client, db, ue = _users_client(_target())
    with patch.object(ue, "get_database", return_value=db), \
         patch.object(ue, "get_tenant_id", return_value="t1"), \
         patch.object(ue, "revoke_user_sessions", new_callable=AsyncMock) as revoke:
        r = client.put(f"/api/users/{TARGET_ID}", json=body)
    assert r.status_code == 200, r.text
    revoke.assert_awaited_once()
    assert revoke.await_args.args[0] == ALICE
    assert reason in revoke.await_args.args[1]


def test_user_update_without_session_impact_does_not_revoke():
    client, db, ue = _users_client(_target())
    with patch.object(ue, "get_database", return_value=db), \
         patch.object(ue, "get_tenant_id", return_value="t1"), \
         patch.object(ue, "revoke_user_sessions", new_callable=AsyncMock) as revoke:
        r = client.put(f"/api/users/{TARGET_ID}", json={"full_name": "Alice B", "role": "Viewer", "status": "active"})
    assert r.status_code == 200, r.text
    revoke.assert_not_awaited()


def test_admin_password_change_writes_the_field_login_reads():
    client, db, ue = _users_client(_target())
    with patch.object(ue, "get_database", return_value=db), \
         patch.object(ue, "get_tenant_id", return_value="t1"), \
         patch.object(ue, "revoke_user_sessions", new_callable=AsyncMock):
        r = client.put(f"/api/users/{TARGET_ID}", json={"password": "N3w-Passw0rd!xyz"})
    assert r.status_code == 200
    update = db.users.update_one.await_args.args[1]
    assert update["$set"]["password"].startswith("$2")
    assert update["$unset"] == {"hashed_password": ""}


def test_admin_password_change_enforces_complexity():
    client, db, ue = _users_client(_target())
    with patch.object(ue, "get_database", return_value=db), \
         patch.object(ue, "get_tenant_id", return_value="t1"):
        r = client.put(f"/api/users/{TARGET_ID}", json={"password": "short"})
    assert r.status_code == 400
    db.users.update_one.assert_not_awaited()


def test_user_delete_revokes_sessions():
    client, db, ue = _users_client(_target())
    with patch.object(ue, "get_database", return_value=db), \
         patch.object(ue, "get_tenant_id", return_value="t1"), \
         patch.object(ue, "revoke_user_sessions", new_callable=AsyncMock) as revoke:
        r = client.delete(f"/api/users/{TARGET_ID}")
    assert r.status_code == 200
    revoke.assert_awaited_once()
    assert revoke.await_args.args[0] == ALICE


# --- directory sign-ins -----------------------------------------------------

def _directory_db(existing):
    db = MagicMock()
    db.users.find_one = AsyncMock(return_value=existing)
    db.sets = []  # copies: the code reuses the $set dict for its return value

    async def _update(_filter, update):
        db.sets.append(dict(update["$set"]))
    db.users.update_one = AsyncMock(side_effect=_update)
    return db


async def test_ldap_sync_keeps_an_admin_disable():
    import ldap_service
    existing = {"_id": "u1", "email": ALICE, "role": "itam_viewer", "status": "Inactive"}
    db = _directory_db(existing)
    syncer = ldap_service.LDAPUserSyncer.__new__(ldap_service.LDAPUserSyncer)
    mapped = {"email": ALICE, "full_name": "Alice", "ldap_dn": "cn=alice", "groups": []}
    with patch.object(ldap_service, "get_database", return_value=db):
        doc = await syncer.sync_user(mapped, "t1")
    assert "status" not in db.sets[-1]
    assert doc["status"] == "Inactive"


async def test_ldap_role_change_revokes_sessions():
    import ldap_service
    existing = {"_id": "u1", "email": ALICE, "role": "itam_viewer", "status": "Active"}
    db = _directory_db(existing)
    syncer = ldap_service.LDAPUserSyncer.__new__(ldap_service.LDAPUserSyncer)
    mapped = {"email": ALICE, "full_name": "Alice", "ldap_dn": "cn=alice", "groups": ["admins"]}
    with patch.object(ldap_service, "get_database", return_value=db), \
         patch("authentication_service.revoke_user_sessions", new_callable=AsyncMock) as revoke:
        await syncer.sync_user(mapped, "t1", role="itam_admin")
        revoke.assert_awaited_once()
        await syncer.sync_user(mapped, "t1", role=None)  # no mapping result: role untouched
        revoke.assert_awaited_once()


async def test_saml_sync_keeps_an_admin_disable():
    import saml_mapping
    existing = {"_id": "u1", "email": ALICE, "role": "itam_viewer", "status": "Inactive"}
    db = _directory_db(existing)
    provisioner = saml_mapping.SAMLUserProvisioner.__new__(saml_mapping.SAMLUserProvisioner)
    mapped = {"email": ALICE, "full_name": "Alice", "nameid": ALICE, "groups": []}
    with patch.object(saml_mapping, "get_database", return_value=db):
        doc = await provisioner.provision_user(mapped, "t1")
    assert "status" not in db.sets[-1]
    assert doc["status"] == "Inactive"


# --- refresh token in an httpOnly cookie --------------------------------------

def _refresh_cookie_header(resp) -> str:
    return next(v for k, v in resp.headers.multi_items() if k == "set-cookie" and v.startswith("omni_refresh="))


def test_login_puts_the_refresh_token_in_an_httponly_cookie():
    db = _login_db(_user(status="Active", mfa={"enabled": False}))
    with patch("authentication_endpoints.get_database", return_value=db):
        r = TestClient(_auth_app()).post("/api/auth/login", json={"email": ALICE, "password": "Password1!"})
    assert r.status_code == 200
    assert "refresh_token" not in r.json()
    cookie = _refresh_cookie_header(r).lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/api/auth" in cookie
    assert "max-age" not in cookie  # ends with the browser session
    assert "secure" not in cookie  # plain-http test client outside production


def test_refresh_cookie_is_secure_in_production():
    from starlette.requests import Request
    from starlette.responses import Response
    req = Request({"type": "http", "scheme": "http", "headers": [], "path": "/"})
    resp = Response()
    with patch.object(auth_svc, "is_production", return_value=True):
        auth_svc.set_refresh_cookie(resp, req, "tok")
    assert "secure" in resp.headers["set-cookie"].lower()


async def _refresh(client, cookie=None, body=None):
    if cookie:
        client.cookies.set("omni_refresh", cookie, path="/api/auth")
    return await client.post("/api/auth/refresh", json=body or {})


async def test_refresh_rotates_the_cookie_and_keeps_mfa_state(live_db):
    from httpx import ASGITransport, AsyncClient
    await live_db._db.users.insert_one({"email": ALICE, "role": "Tenant Admin", "tenantId": "t1", "status": "Active"})
    first = auth_svc.create_refresh_token({"sub": ALICE, "mfa_verified": True})
    with patch("authentication_endpoints.get_database", return_value=live_db):
        async with AsyncClient(transport=ASGITransport(app=_auth_app()), base_url="http://t") as client:
            r = await _refresh(client, cookie=first)
            assert r.status_code == 200
            assert "refresh_token" not in r.json()
            access = _jwt.decode(r.json()["access_token"], auth_svc.SECRET_KEY, algorithms=[auth_svc.ALGORITHM])
            assert access["mfa_verified"] is True
            rotated = r.cookies.get("omni_refresh")
            assert rotated and rotated != first
            assert _jwt.decode(rotated, auth_svc.SECRET_KEY, algorithms=[auth_svc.ALGORITHM])["mfa_verified"] is True
            client.cookies.clear()
            replay = await _refresh(client, cookie=first)  # single use
            assert replay.status_code == 401


async def test_refresh_still_accepts_a_legacy_body_token(live_db):
    from httpx import ASGITransport, AsyncClient
    await live_db._db.users.insert_one({"email": ALICE, "role": "Viewer", "tenantId": "t1", "status": "Active"})
    legacy = auth_svc.create_refresh_token({"sub": ALICE})
    with patch("authentication_endpoints.get_database", return_value=live_db):
        async with AsyncClient(transport=ASGITransport(app=_auth_app()), base_url="http://t") as client:
            r = await _refresh(client, body={"refresh_token": legacy})
    assert r.status_code == 200
    assert r.cookies.get("omni_refresh")  # moved over to the cookie


async def test_logout_with_an_expired_access_token_still_ends_the_session(live_db):
    from datetime import timedelta
    from httpx import ASGITransport, AsyncClient
    await live_db._db.users.insert_one({"email": ALICE, "role": "Viewer", "tenantId": "t1", "status": "Active"})
    refresh = auth_svc.create_refresh_token({"sub": ALICE})
    expired = auth_svc.create_access_token({"sub": ALICE, "role": "Viewer", "tenant_id": "t1"}, expires_delta=timedelta(seconds=-5))
    with patch("authentication_endpoints.get_database", return_value=live_db):
        async with AsyncClient(transport=ASGITransport(app=_auth_app()), base_url="http://t") as client:
            client.cookies.set("omni_refresh", refresh, path="/api/auth")
            out = await client.post("/api/auth/logout", headers={"Authorization": f"Bearer {expired}"})
            assert out.status_code == 200
            assert 'omni_refresh=""' in _refresh_cookie_header(out) or "max-age=0" in _refresh_cookie_header(out).lower()
            client.cookies.clear()
            again = await _refresh(client, cookie=refresh)
    assert again.status_code == 401  # the refresh token was revoked, not just forgotten


async def test_logout_revokes_a_valid_access_token(live_db):
    from httpx import ASGITransport, AsyncClient
    access = _access(ALICE)
    with patch("authentication_endpoints.get_database", return_value=live_db):
        async with AsyncClient(transport=ASGITransport(app=_auth_app()), base_url="http://t") as client:
            out = await client.post("/api/auth/logout", headers={"Authorization": f"Bearer {access}"})
    assert out.status_code == 200
    auth_svc._revoked_jti_cache.clear()
    assert await _rejected(access)
