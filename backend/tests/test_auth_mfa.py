"""
Unit tests for authentication and MFA endpoints.

These tests mount only the relevant routers on a minimal FastAPI app and
patch get_database() / external services so no real MongoDB is required.
"""
import sys
import os

# Ensure the backend directory is importable when run from the project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest


@pytest.fixture(autouse=True)
def _reset_shared_rate_limiter():
    """authentication_endpoints.router's and mfa_endpoints.router's
    @limiter.limit(...) decorators bind to the single process-wide
    rate_limiter.limiter singleton at import time (not the per-test
    Limiter() built by _make_auth_app()/_make_mfa_app()) — without resetting
    it between tests, calls accumulate across this whole test class and can
    trip the limit for an unrelated later test. Same isolation pattern as
    test_mfa.py's _reset_shared_rate_limiter / test_ldap_service.py's
    _reset_ldap_rate_limit."""
    from rate_limiter import limiter as shared_limiter
    shared_limiter._storage.reset()
    yield
    shared_limiter._storage.reset()


# ---------------------------------------------------------------------------
# Helpers for building DB mocks
# ---------------------------------------------------------------------------

def _make_db_mock(user=None, role_obj=None, login_record=None):
    """Return a minimal async DB mock that supports the auth query surface."""
    col = MagicMock()
    col.find_one = AsyncMock(return_value=None)
    col.update_one = AsyncMock()
    col.delete_one = AsyncMock()

    raw_db = MagicMock()
    raw_db.users = MagicMock()
    raw_db.users.find_one = AsyncMock(return_value=user)
    raw_db.login_attempts = MagicMock()
    raw_db.login_attempts.find_one = AsyncMock(return_value=login_record)
    raw_db.login_attempts.update_one = AsyncMock()
    raw_db.login_attempts.delete_one = AsyncMock()

    db = MagicMock()
    db._db = raw_db
    db.users = MagicMock()
    db.users.find_one = AsyncMock(return_value=user)
    db.users.update_one = AsyncMock()
    db.roles = MagicMock()
    db.roles.find_one = AsyncMock(return_value=role_obj)
    db.login_events = MagicMock()
    db.login_events.update_one = AsyncMock()
    return db


def _make_hashed_user(email="user@example.com", role="Viewer", tenant_id="t1"):
    """Minimal user document with a pre-hashed password ('Password1!')."""
    from auth_utils import hash_password
    return {
        "_id": "mock_id",
        "id": "mock_id",
        "email": email,
        "username": email,
        "password": hash_password("Password1!"),
        "role": role,
        "tenantId": tenant_id,
        "mfa": {"enabled": False},
    }


def _make_auth_app():
    """Minimal FastAPI app with only the auth router and SlowAPI middleware."""
    import authentication_endpoints as auth_ep
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware

    mini = FastAPI()
    # Use a fresh limiter with no storage so tests don't share state
    test_limiter = Limiter(key_func=get_remote_address)
    mini.state.limiter = test_limiter
    mini.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    mini.add_middleware(SlowAPIMiddleware)
    mini.include_router(auth_ep.router)
    return mini


def _make_mfa_app():
    """Minimal FastAPI app with only the MFA router and SlowAPI middleware."""
    import mfa_endpoints
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware

    mini = FastAPI()
    test_limiter = Limiter(key_func=get_remote_address)
    mini.state.limiter = test_limiter
    mini.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    mini.add_middleware(SlowAPIMiddleware)
    mini.include_router(mfa_endpoints.router)
    return mini


# ===========================================================================
# Password complexity tests (pure function — no mocking needed)
# ===========================================================================

class TestPasswordComplexity:

    def test_too_short(self):
        from auth_utils import validate_password_complexity
        assert validate_password_complexity("Ab1!") is not None

    def test_no_uppercase(self):
        from auth_utils import validate_password_complexity
        assert validate_password_complexity("password1!") is not None

    def test_no_lowercase(self):
        from auth_utils import validate_password_complexity
        assert validate_password_complexity("PASSWORD1!") is not None

    def test_no_digit(self):
        from auth_utils import validate_password_complexity
        assert validate_password_complexity("Password!") is not None

    def test_no_special(self):
        from auth_utils import validate_password_complexity
        assert validate_password_complexity("Password1") is not None

    def test_valid(self):
        from auth_utils import validate_password_complexity
        assert validate_password_complexity("Password1!") is None

    def test_valid_long(self):
        from auth_utils import validate_password_complexity
        assert validate_password_complexity("MySecureP@ssw0rd2030!") is None


# ===========================================================================
# Login endpoint tests
# ===========================================================================

class TestLoginEndpoint:

    def test_login_success_returns_token(self):
        user = _make_hashed_user()
        db = _make_db_mock(user=user)
        app = _make_auth_app()

        with patch("authentication_endpoints.get_database", return_value=db):
            with TestClient(app) as client:
                resp = client.post("/api/auth/login", json={"email": "user@example.com", "password": "Password1!"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "access_token" in body
        assert body["access_token"] != ""
        assert body["token_type"] == "bearer"

    def test_login_wrong_password_returns_401(self):
        user = _make_hashed_user()
        db = _make_db_mock(user=user)
        app = _make_auth_app()

        with patch("authentication_endpoints.get_database", return_value=db):
            with TestClient(app) as client:
                resp = client.post("/api/auth/login", json={"email": "user@example.com", "password": "WrongPass1!"})

        assert resp.status_code == 401
        assert "credentials" in resp.json()["detail"].lower()

    def test_login_unknown_user_returns_401(self):
        db = _make_db_mock(user=None)
        app = _make_auth_app()

        with patch("authentication_endpoints.get_database", return_value=db):
            with TestClient(app) as client:
                resp = client.post("/api/auth/login", json={"email": "ghost@example.com", "password": "Password1!"})

        assert resp.status_code == 401

    def test_login_missing_identifier_returns_401_or_422(self):
        db = _make_db_mock()
        app = _make_auth_app()

        with patch("authentication_endpoints.get_database", return_value=db):
            with TestClient(app) as client:
                resp = client.post("/api/auth/login", json={"password": "Password1!"})

        # Pydantic v2 accepts the request (both fields optional); identifier is None → 401
        assert resp.status_code in (401, 422)

    def test_login_locked_account_returns_429(self):
        import datetime
        from datetime import timezone
        future = (datetime.datetime.now(timezone.utc) + datetime.timedelta(minutes=10)).isoformat()
        lock_record = {"identifier": "user@example.com", "locked_until": future, "attempts": []}
        db = _make_db_mock(user=_make_hashed_user(), login_record=lock_record)
        app = _make_auth_app()

        with patch("authentication_endpoints.get_database", return_value=db):
            with TestClient(app) as client:
                resp = client.post("/api/auth/login", json={"email": "user@example.com", "password": "Password1!"})

        assert resp.status_code == 429

    def test_login_expired_lock_allows_login(self):
        import datetime
        from datetime import timezone
        past = (datetime.datetime.now(timezone.utc) - datetime.timedelta(minutes=5)).isoformat()
        lock_record = {"identifier": "user@example.com", "locked_until": past, "attempts": []}
        db = _make_db_mock(user=_make_hashed_user(), login_record=lock_record)
        app = _make_auth_app()

        with patch("authentication_endpoints.get_database", return_value=db):
            with TestClient(app) as client:
                resp = client.post("/api/auth/login", json={"email": "user@example.com", "password": "Password1!"})

        assert resp.status_code == 200

    def test_login_mfa_required_returns_mfa_token(self):
        user = _make_hashed_user()
        user["mfa"] = {"enabled": True}
        db = _make_db_mock(user=user)
        app = _make_auth_app()

        with patch("authentication_endpoints.get_database", return_value=db), \
             patch("mfa_service.create_mfa_session", new_callable=AsyncMock, return_value="mock-mfa-session-token"):
            with TestClient(app) as client:
                resp = client.post("/api/auth/login", json={"email": "user@example.com", "password": "Password1!"})

        assert resp.status_code == 200
        body = resp.json()
        assert body.get("mfa_required") is True
        assert body.get("token_type") == "mfa_required"
        assert body.get("mfa_session_token") == "mock-mfa-session-token"
        assert body.get("access_token") == ""

    def test_login_mfa_session_db_failure_returns_503(self):
        """WR-07: create_mfa_session is a real async Mongo call — a driver
        connectivity/timeout error must surface as the intended 503, not an
        unhandled 500 (the prior except-ImportError-only clause never caught
        this failure mode)."""
        from pymongo.errors import PyMongoError

        user = _make_hashed_user()
        user["mfa"] = {"enabled": True}
        db = _make_db_mock(user=user)
        app = _make_auth_app()

        with patch("authentication_endpoints.get_database", return_value=db), \
             patch("mfa_service.create_mfa_session", new_callable=AsyncMock,
                   side_effect=PyMongoError("connection lost")):
            with TestClient(app) as client:
                resp = client.post("/api/auth/login", json={"email": "user@example.com", "password": "Password1!"})

        assert resp.status_code == 503

    def test_login_returns_user_without_sensitive_fields(self):
        user = _make_hashed_user()
        db = _make_db_mock(user=user)
        app = _make_auth_app()

        with patch("authentication_endpoints.get_database", return_value=db):
            with TestClient(app) as client:
                resp = client.post("/api/auth/login", json={"email": "user@example.com", "password": "Password1!"})

        assert resp.status_code == 200
        returned_user = resp.json()["user"]
        assert "password" not in returned_user
        assert "mfa" not in returned_user


# ===========================================================================
# MFA endpoint tests
# ===========================================================================

class TestMFAVerifyLogin:

    def _make_authenticated_mfa_app(self, db_mock):
        """Build MFA app with mocked get_current_user (skips JWT validation)."""
        from auth_types import TokenData
        from authentication_service import get_current_user

        mock_token_data = TokenData(
            username="user@example.com",
            role="Viewer",
            tenant_id="t1",
            mfa_verified=True,
        )

        app = _make_mfa_app()
        app.dependency_overrides[get_current_user] = lambda: mock_token_data

        return app

    def test_verify_mfa_login_success(self):
        user = _make_hashed_user()
        db = _make_db_mock(user=user)
        app = _make_mfa_app()

        with patch("mfa_endpoints.get_database", return_value=db), \
             patch("mfa_service.verify_mfa_token", new_callable=AsyncMock,
                   return_value={"success": True, "email": "user@example.com"}):
            with TestClient(app) as client:
                resp = client.post(
                    "/api/mfa/verify",
                    json={"session_token": "valid-session", "code": "123456", "use_backup_code": False},
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    def test_verify_mfa_login_wrong_code(self):
        db = _make_db_mock()
        app = _make_mfa_app()

        with patch("mfa_endpoints.get_database", return_value=db), \
             patch("mfa_service.verify_mfa_token", new_callable=AsyncMock,
                   return_value={"success": False, "error": "Invalid TOTP code"}):
            with TestClient(app) as client:
                resp = client.post(
                    "/api/mfa/verify",
                    json={"session_token": "bad-session", "code": "000000", "use_backup_code": False},
                )

        assert resp.status_code == 401

    def test_verify_mfa_login_wrong_code_records_login_failure(self):
        """WR-04: a wrong TOTP code must be folded into the shared login
        lockout counter, keyed by the account email resolved from the
        session — the same bookkeeping /api/auth/login uses for wrong
        passwords — so repeated correct-password/wrong-TOTP round trips
        eventually lock the account out via the next /api/auth/login call."""
        db = _make_db_mock()
        app = _make_mfa_app()

        with patch("mfa_endpoints.get_database", return_value=db), \
             patch("mfa_service.verify_mfa_token", new_callable=AsyncMock,
                   return_value={"success": False, "error": "Invalid TOTP code", "email": "user@example.com"}):
            with TestClient(app) as client:
                resp = client.post(
                    "/api/mfa/verify",
                    json={"session_token": "bad-session", "code": "000000", "use_backup_code": False},
                )

        assert resp.status_code == 401
        db._db.login_attempts.update_one.assert_awaited_once()
        filter_arg = db._db.login_attempts.update_one.call_args.args[0]
        assert filter_arg == {"identifier": "user@example.com"}

    def test_verify_mfa_login_wrong_backup_code_records_login_failure(self):
        db = _make_db_mock()
        app = _make_mfa_app()

        with patch("mfa_endpoints.get_database", return_value=db), \
             patch("mfa_service.validate_mfa_session", new_callable=AsyncMock, return_value="user@example.com"), \
             patch("mfa_service.use_backup_code", new_callable=AsyncMock, return_value=False):
            with TestClient(app) as client:
                resp = client.post(
                    "/api/mfa/verify",
                    json={"session_token": "valid-session", "code": "WRONGCODE", "use_backup_code": True},
                )

        assert resp.status_code == 401
        db._db.login_attempts.update_one.assert_awaited_once()

    def test_verify_mfa_login_success_clears_login_failures(self):
        user = _make_hashed_user()
        db = _make_db_mock(user=user)
        app = _make_mfa_app()

        with patch("mfa_endpoints.get_database", return_value=db), \
             patch("mfa_service.verify_mfa_token", new_callable=AsyncMock,
                   return_value={"success": True, "email": "user@example.com"}):
            with TestClient(app) as client:
                resp = client.post(
                    "/api/mfa/verify",
                    json={"session_token": "valid-session", "code": "123456", "use_backup_code": False},
                )

        assert resp.status_code == 200
        db._db.login_attempts.delete_one.assert_awaited_once_with({"identifier": "user@example.com"})

    def test_verify_mfa_login_backup_code_success(self):
        user = _make_hashed_user()
        db = _make_db_mock(user=user)
        app = _make_mfa_app()

        with patch("mfa_endpoints.get_database", return_value=db), \
             patch("mfa_service.validate_mfa_session", new_callable=AsyncMock, return_value="user@example.com"), \
             patch("mfa_service.use_backup_code", new_callable=AsyncMock, return_value=True), \
             patch("mfa_service.consume_mfa_session", new_callable=AsyncMock):
            with TestClient(app) as client:
                resp = client.post(
                    "/api/mfa/verify",
                    json={"session_token": "valid-session", "code": "BACKUP001", "use_backup_code": True},
                )

        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_verify_mfa_login_invalid_session(self):
        db = _make_db_mock()
        app = _make_mfa_app()

        with patch("mfa_endpoints.get_database", return_value=db), \
             patch("mfa_service.validate_mfa_session", new_callable=AsyncMock, return_value=None):
            with TestClient(app) as client:
                resp = client.post(
                    "/api/mfa/verify",
                    json={"session_token": "expired-session", "code": "BACKUP001", "use_backup_code": True},
                )

        assert resp.status_code == 401

    def test_verify_mfa_user_not_found_returns_404(self):
        db = _make_db_mock(user=None)
        app = _make_mfa_app()

        with patch("mfa_endpoints.get_database", return_value=db), \
             patch("mfa_service.verify_mfa_token", new_callable=AsyncMock,
                   return_value={"success": True, "email": "ghost@example.com"}):
            with TestClient(app) as client:
                resp = client.post(
                    "/api/mfa/verify",
                    json={"session_token": "valid-session", "code": "123456", "use_backup_code": False},
                )

        assert resp.status_code == 404

    def test_mfa_status_returns_enabled_flag(self):
        user = _make_hashed_user()
        db = _make_db_mock(user=user)
        app = self._make_authenticated_mfa_app(db)

        with patch("mfa_endpoints.get_database", return_value=db), \
             patch("mfa_service.get_mfa_status", new_callable=AsyncMock,
                   return_value={"enabled": False, "backup_codes_remaining": 0}):
            with TestClient(app) as client:
                resp = client.get(
                    "/api/mfa/status",
                    headers={"Authorization": "Bearer fake-jwt"},
                )

        assert resp.status_code == 200
        assert "enabled" in resp.json()
