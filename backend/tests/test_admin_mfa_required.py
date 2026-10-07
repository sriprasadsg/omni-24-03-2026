"""
Admin-tier sessions must pass MFA.

An admin-tier token without mfa_verified gets 403 (X-MFA-Required) on every
route except who-am-I, MFA status, enrollment and step-up. Enrolling or
stepping up returns an MFA-verified token, and refreshes keep it verified
(see test_session_revocation). Non-admin roles are unaffected. Hermetic: the
revocation lookup fails open without Mongo, and MFA storage is mocked.
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

EMAIL = "admin@mfa.test"


def _token(role, **claims):
    return auth_svc.create_access_token({"sub": EMAIL, "role": role, "tenant_id": "t1", **claims})


def _claims(token):
    return _jwt.decode(token, auth_svc.SECRET_KEY, algorithms=[auth_svc.ALGORITHM])


@pytest.fixture(autouse=True)
def _no_revocation_db():
    db = MagicMock()
    db._db.revoked_tokens.find_one = AsyncMock(return_value=None)
    cursor = MagicMock()
    cursor.limit.return_value.__aiter__ = lambda self: iter([])
    db._db.revoked_tokens.find.return_value = cursor
    with patch("database.get_database", return_value=db):
        yield


@pytest.mark.parametrize("role", ["Super Admin", "platform-admin", "Tenant Admin", "admin", "Admin", "itam_admin"])
async def test_admin_session_without_mfa_is_refused(role):
    with pytest.raises(HTTPException) as exc:
        await auth_svc.get_current_user(_token(role))
    assert exc.value.status_code == 403
    assert exc.value.headers["X-MFA-Required"] == "1"
    with pytest.raises(HTTPException):  # websocket / socket.io path too
        auth_svc.verify_token(_token(role))


@pytest.mark.parametrize("role", ["Super Admin", "Tenant Admin", "itam_admin"])
async def test_admin_session_with_mfa_is_allowed(role):
    assert (await auth_svc.get_current_user(_token(role, mfa_verified=True))).role == role


@pytest.mark.parametrize("role", ["Viewer", "user", "analyst", "security_analyst", "itam_viewer"])
async def test_other_roles_do_not_need_mfa(role):
    assert (await auth_svc.get_current_user(_token(role))).role == role


async def test_enrollment_routes_accept_a_pending_admin_session():
    user = await auth_svc.get_current_user_mfa_pending(_token("Tenant Admin"))
    assert user.mfa_verified is False


@pytest.mark.parametrize("role,verified,enabled,action", [
    ("Tenant Admin", False, False, "enroll"),
    ("Tenant Admin", False, True, "verify"),
    ("Tenant Admin", True, True, None),
    ("Viewer", False, False, None),
])
def test_mfa_action(role, verified, enabled, action):
    assert auth_svc.mfa_action_for(role, verified, enabled) == action


# --- endpoints ----------------------------------------------------------------

def _app():
    import authentication_endpoints as auth_ep
    import mfa_endpoints
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address
    from rate_limiter import limiter as shared_limiter
    shared_limiter._storage.reset()
    app = FastAPI()
    app.state.limiter = Limiter(key_func=get_remote_address)
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(auth_ep.router)
    app.include_router(mfa_endpoints.router)
    return TestClient(app)


def _user(mfa_enabled=False):
    return {"_id": "u1", "email": EMAIL, "role": "Tenant Admin", "tenantId": "t1", "status": "Active",
            "mfa": {"enabled": mfa_enabled}}


def _db(user):
    db = MagicMock()
    db.users.find_one = AsyncMock(return_value=user)
    db.users.update_one = AsyncMock()
    db._db.users.find_one = AsyncMock(return_value=user)
    db._db.login_attempts.find_one = AsyncMock(return_value=None)
    db._db.login_attempts.update_one = AsyncMock()
    db._db.login_attempts.delete_one = AsyncMock()
    db._db.roles.find_one = AsyncMock(return_value=None)
    db.roles.find_one = AsyncMock(return_value=None)
    return db


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_me_tells_a_pending_admin_to_enroll():
    db = _db(_user())
    with patch("authentication_endpoints.get_database", return_value=db):
        r = _app().get("/api/auth/me", headers=_auth(_token("Tenant Admin")))
    assert r.status_code == 200
    assert r.json()["mfa_action"] == "enroll"


def test_me_tells_an_enrolled_but_unverified_admin_to_step_up():
    db = _db(_user(mfa_enabled=True))
    with patch("authentication_endpoints.get_database", return_value=db):
        r = _app().get("/api/auth/me", headers=_auth(_token("Tenant Admin")))
    assert r.json()["mfa_action"] == "verify"


def test_password_login_of_an_admin_without_mfa_says_enroll():
    from auth_utils import hash_password
    user = {**_user(), "password": hash_password("Password1!")}
    db = _db(user)
    db.login_events.update_one = AsyncMock()
    with patch("authentication_endpoints.get_database", return_value=db):
        r = _app().post("/api/auth/login", json={"email": EMAIL, "password": "Password1!"})
    assert r.status_code == 200
    assert r.json()["user"]["mfa_action"] == "enroll"


def test_enrolling_upgrades_the_session():
    db = _db(_user())
    with patch("mfa_endpoints.get_database", return_value=db), \
         patch("mfa_service.enroll_mfa", new_callable=AsyncMock, return_value={"success": True, "backup_codes": ["1"]}):
        r = _app().post("/api/mfa/verify-setup", json={"totp_code": "123456"}, headers=_auth(_token("Tenant Admin")))
    assert r.status_code == 200, r.text
    assert _claims(r.json()["access_token"])["mfa_verified"] is True
    assert _claims(r.cookies.get("omni_refresh"))["mfa_verified"] is True


@pytest.mark.parametrize("path,body", [("/api/mfa/setup", {"password": "Password1!"}),
                                       ("/api/mfa/verify-setup", {"totp_code": "123456", "password": "Password1!"})])
def test_unverified_session_cannot_replace_an_existing_authenticator(path, body):
    db = _db(_user(mfa_enabled=True))
    with patch("mfa_endpoints.get_database", return_value=db), \
         patch("mfa_service.enroll_mfa", new_callable=AsyncMock) as enroll:
        r = _app().post(path, json=body, headers=_auth(_token("Tenant Admin")))
    assert r.status_code == 403
    enroll.assert_not_awaited()
    db.users.update_one.assert_not_awaited()


def test_step_up_with_a_valid_code_returns_a_verified_session():
    db = _db(_user(mfa_enabled=True))
    with patch("mfa_endpoints.get_database", return_value=db), \
         patch("authentication_endpoints.get_database", return_value=db), \
         patch("mfa_service.create_mfa_session", new_callable=AsyncMock, return_value="s1"), \
         patch("mfa_service.verify_mfa_token", new_callable=AsyncMock, return_value={"success": True, "email": EMAIL}) as verify:
        r = _app().post("/api/mfa/step-up", json={"code": "123456"}, headers=_auth(_token("Tenant Admin")))
    assert r.status_code == 200, r.text
    verify.assert_awaited_once_with("s1", "123456")
    token = r.json()["access_token"]
    assert _claims(token)["mfa_verified"] is True
    assert _claims(token)["role"] == "Tenant Admin"


def test_step_up_with_a_wrong_code_counts_as_a_failed_login():
    db = _db(_user(mfa_enabled=True))
    with patch("mfa_endpoints.get_database", return_value=db), \
         patch("authentication_endpoints.get_database", return_value=db), \
         patch("mfa_service.create_mfa_session", new_callable=AsyncMock, return_value="s1"), \
         patch("mfa_service.verify_mfa_token", new_callable=AsyncMock, return_value={"success": False}):
        r = _app().post("/api/mfa/step-up", json={"code": "000000"}, headers=_auth(_token("Tenant Admin")))
    assert r.status_code == 400
    db._db.login_attempts.update_one.assert_awaited()


def test_pending_admin_cannot_disable_mfa_or_use_other_routes():
    r = _app().post("/api/mfa/disable", json={"password": "x"}, headers=_auth(_token("Tenant Admin")))
    assert r.status_code == 403
    assert r.headers.get("X-MFA-Required") == "1"
