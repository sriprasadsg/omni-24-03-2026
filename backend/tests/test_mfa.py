"""
Unit tests for mfa_service.py and mfa_endpoints.py.

Covers: enrollment, verification, backup codes, disable, regenerate,
encryption enforcement (no base64 fallback), MongoDB TTL session storage,
and the encryption_service health check.

No real MongoDB required — DB calls are mocked via unittest.mock.
"""
import sys
import os
import datetime as _dt

# Ensure the backend directory is importable when run from the project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

import mfa_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _col():
    """A collection mock supporting the async surface mfa_service uses."""
    col = MagicMock()
    col.find_one = AsyncMock(return_value=None)
    col.find_one_and_delete = AsyncMock(return_value=None)
    col.insert_one = AsyncMock()
    col.delete_one = AsyncMock()
    col.delete_many = AsyncMock(return_value=MagicMock(deleted_count=0))
    col.update_one = AsyncMock()
    col.create_index = AsyncMock()
    return col


def _db_mock(user=None, mfa_sessions_col=None):
    """A db-handle mock: db.users (tenant-scoped) + db._db.mfa_sessions (raw)."""
    db = MagicMock()
    db.users = MagicMock()
    db.users.find_one = AsyncMock(return_value=user)
    db.users.update_one = AsyncMock()
    # Default: the atomic find_one_and_update "succeeds" (returns the matched
    # doc) whenever a user is present, mirroring real Mongo semantics for a
    # matching filter — individual tests override this to simulate a race.
    db.users.find_one_and_update = AsyncMock(return_value=user)
    raw = MagicMock()
    raw.mfa_sessions = mfa_sessions_col or _col()
    db._db = raw
    return db


def _hashed_password_user(email="user@example.com", password="Password1!", **mfa_overrides):
    from auth_utils import hash_password
    mfa = {
        "enabled": True,
        "secret_encrypted": mfa_service._encrypt_secret("JBSWY3DPEHPK3PXP"),
        "backup_codes_hashed": [],
    }
    mfa.update(mfa_overrides)
    return {
        "_id": "id1",
        "email": email,
        "password": hash_password(password),
        "role": "Viewer",
        "tenantId": "t1",
        "mfa": mfa,
    }


@pytest.fixture(autouse=True)
def _reset_mfa_index_flag():
    """Reset the lazy TTL-index-created flag between tests."""
    mfa_service._mfa_index_created = False
    yield
    mfa_service._mfa_index_created = False


@pytest.fixture(autouse=True)
def _reset_shared_rate_limiter():
    """mfa_endpoints.router's @limiter.limit(...) decorators bind to the single
    process-wide rate_limiter.limiter singleton at import time (not the
    per-test Limiter() built in TestMFAEndpoints._app()) — same isolation
    pattern as test_ldap_service.py's _reset_ldap_rate_limit."""
    from rate_limiter import limiter as shared_limiter
    shared_limiter._storage.reset()
    yield
    shared_limiter._storage.reset()


# ===========================================================================
# Encryption enforcement (Pitfall 2)
# ===========================================================================

class TestEncryption:

    def test_encrypt_decrypt_round_trip(self):
        ciphertext = mfa_service._encrypt_secret("MYSECRET123")
        assert ciphertext != "MYSECRET123"
        assert mfa_service._decrypt_secret(ciphertext) == "MYSECRET123"

    def test_encrypted_secret_is_not_base64_of_plaintext(self):
        """Regression guard for Pitfall 2: ciphertext must not be recoverable
        via a bare base64 decode (the old silent fallback behavior)."""
        import base64
        ciphertext = mfa_service._encrypt_secret("PLAINSECRET")
        try:
            decoded = base64.b64decode(ciphertext.encode()).decode(errors="ignore")
        except Exception:
            decoded = ""
        assert decoded != "PLAINSECRET"

    def test_verify_encryption_service_health_check_passes(self):
        # Should not raise when encryption_service is available (dev ephemeral
        # key or a real PAYMENT_ENCRYPTION_KEY — either way round-trips).
        mfa_service.verify_encryption_service()

    def test_verify_encryption_service_raises_on_broken_roundtrip(self):
        broken_svc = MagicMock()
        broken_svc.encrypt.return_value = "ciphertext"
        broken_svc.decrypt.return_value = "NOT-THE-SAME-PROBE"
        with patch("mfa_service.get_encryption_service", return_value=broken_svc):
            with pytest.raises(RuntimeError):
                mfa_service.verify_encryption_service()

    def test_no_silent_fallback_when_encryption_service_unavailable(self):
        """If encryption_service itself raises, _encrypt_secret must propagate
        the error rather than degrading to a base64 fallback (Pitfall 2)."""
        with patch("mfa_service.get_encryption_service", side_effect=RuntimeError("key missing")):
            with pytest.raises(RuntimeError):
                mfa_service._encrypt_secret("secret")


# ===========================================================================
# Backup codes
# ===========================================================================

class TestBackupCodes:

    def test_generate_backup_codes_format(self):
        codes = mfa_service.generate_backup_codes()
        assert len(codes) == 8
        assert len(set(codes)) == 8  # extremely likely unique
        for c in codes:
            assert len(c) == 8
            assert c.isdigit()

    def test_hash_backup_code_is_not_reversible_plaintext(self):
        h = mfa_service._hash_backup_code("12345678")
        assert h != "12345678"
        assert mfa_service._verify_backup_code("12345678", h) is True
        assert mfa_service._verify_backup_code("87654321", h) is False

    @pytest.mark.asyncio
    async def test_use_backup_code_success_consumes_code(self):
        code_hash = mfa_service._hash_backup_code("11112222")
        user = _hashed_password_user(backup_codes_hashed=[code_hash])
        db = _db_mock(user=user)
        with patch("mfa_service.get_database", return_value=db):
            ok = await mfa_service.use_backup_code("user@example.com", "11112222")
        assert ok is True
        # WR-01: consumption is atomic — a single find_one_and_update that both
        # matches on the exact hash and $pulls it, not a read-then-replace-array.
        db.users.find_one_and_update.assert_awaited_once()
        filter_arg, update_arg = db.users.find_one_and_update.call_args.args[:2]
        assert filter_arg == {"email": "user@example.com", "mfa.backup_codes_hashed": code_hash}
        assert update_arg["$pull"] == {"mfa.backup_codes_hashed": code_hash}
        db.users.update_one.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_use_backup_code_toctou_race_loses_atomic_update_returns_false(self):
        """WR-01 regression guard: if a concurrent request already consumed the
        code between the initial read and the atomic $pull (find_one_and_update
        matches nothing and returns None), use_backup_code must report failure
        rather than a false-positive success."""
        code_hash = mfa_service._hash_backup_code("11112222")
        user = _hashed_password_user(backup_codes_hashed=[code_hash])
        db = _db_mock(user=user)
        db.users.find_one_and_update = AsyncMock(return_value=None)
        with patch("mfa_service.get_database", return_value=db):
            ok = await mfa_service.use_backup_code("user@example.com", "11112222")
        assert ok is False

    @pytest.mark.asyncio
    async def test_use_backup_code_wrong_code_fails(self):
        code_hash = mfa_service._hash_backup_code("11112222")
        user = _hashed_password_user(backup_codes_hashed=[code_hash])
        db = _db_mock(user=user)
        with patch("mfa_service.get_database", return_value=db):
            ok = await mfa_service.use_backup_code("user@example.com", "99999999")
        assert ok is False

    @pytest.mark.asyncio
    async def test_use_backup_code_mfa_not_enabled_returns_false(self):
        user = _hashed_password_user()
        user["mfa"]["enabled"] = False
        db = _db_mock(user=user)
        with patch("mfa_service.get_database", return_value=db):
            ok = await mfa_service.use_backup_code("user@example.com", "11112222")
        assert ok is False


# ===========================================================================
# MFA sessions — MongoDB TTL storage (Pitfall 1)
# ===========================================================================

class TestMFASessionsTTL:

    @pytest.mark.asyncio
    async def test_create_mfa_session_persists_to_mongo_not_memory(self):
        col = _col()
        db = _db_mock(mfa_sessions_col=col)
        with patch("mfa_service.get_database", return_value=db):
            token = await mfa_service.create_mfa_session("user@example.com")
        assert token
        col.insert_one.assert_awaited_once()
        inserted = col.insert_one.call_args.args[0]
        assert inserted["_id"] == token
        assert inserted["email"] == "user@example.com"
        assert "expires_at" in inserted
        # Not stored in the old in-memory dict at all
        assert not hasattr(mfa_service, "_mfa_sessions")

    @pytest.mark.asyncio
    async def test_create_mfa_session_ensures_ttl_index(self):
        col = _col()
        db = _db_mock(mfa_sessions_col=col)
        with patch("mfa_service.get_database", return_value=db):
            await mfa_service.create_mfa_session("user@example.com")
        col.create_index.assert_awaited_once_with("expires_at", expireAfterSeconds=0)

    @pytest.mark.asyncio
    async def test_validate_mfa_session_valid_returns_email(self):
        col = _col()
        future = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(minutes=4)
        col.find_one = AsyncMock(return_value={"_id": "tok1", "email": "user@example.com", "expires_at": future})
        db = _db_mock(mfa_sessions_col=col)
        with patch("mfa_service.get_database", return_value=db):
            email = await mfa_service.validate_mfa_session("tok1")
        assert email == "user@example.com"

    @pytest.mark.asyncio
    async def test_validate_mfa_session_missing_returns_none(self):
        col = _col()
        db = _db_mock(mfa_sessions_col=col)
        with patch("mfa_service.get_database", return_value=db):
            email = await mfa_service.validate_mfa_session("no-such-token")
        assert email is None

    @pytest.mark.asyncio
    async def test_validate_mfa_session_expired_returns_none_and_deletes(self):
        col = _col()
        past = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(seconds=5)
        col.find_one = AsyncMock(return_value={"_id": "tok1", "email": "user@example.com", "expires_at": past})
        db = _db_mock(mfa_sessions_col=col)
        with patch("mfa_service.get_database", return_value=db):
            email = await mfa_service.validate_mfa_session("tok1")
        assert email is None
        col.delete_one.assert_awaited_once_with({"_id": "tok1"})

    @pytest.mark.asyncio
    async def test_validate_mfa_session_handles_naive_datetime_from_motor(self):
        """Motor returns naive UTC datetimes by default (no tz_aware=True) —
        must not raise when comparing a naive expires_at."""
        col = _col()
        future_naive = _dt.datetime.utcnow() + _dt.timedelta(minutes=4)
        col.find_one = AsyncMock(return_value={"_id": "tok1", "email": "user@example.com", "expires_at": future_naive})
        db = _db_mock(mfa_sessions_col=col)
        with patch("mfa_service.get_database", return_value=db):
            email = await mfa_service.validate_mfa_session("tok1")
        assert email == "user@example.com"

    @pytest.mark.asyncio
    async def test_consume_mfa_session_deletes_document(self):
        col = _col()
        db = _db_mock(mfa_sessions_col=col)
        with patch("mfa_service.get_database", return_value=db):
            await mfa_service.consume_mfa_session("tok1")
        col.delete_one.assert_awaited_once_with({"_id": "tok1"})

    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions_deletes_matching_docs(self):
        col = _col()
        col.delete_many = AsyncMock(return_value=MagicMock(deleted_count=3))
        db = _db_mock(mfa_sessions_col=col)
        with patch("mfa_service.get_database", return_value=db):
            count = await mfa_service.cleanup_expired_sessions()
        assert count == 3
        col.delete_many.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_verify_mfa_token_success(self):
        col = _col()
        future = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(minutes=4)
        col.find_one_and_delete = AsyncMock(
            return_value={"_id": "tok1", "email": "user@example.com", "expires_at": future}
        )
        user = _hashed_password_user()
        db = _db_mock(user=user, mfa_sessions_col=col)
        with patch("mfa_service.get_database", return_value=db), \
             patch("mfa_service.verify_totp_code", return_value=True):
            result = await mfa_service.verify_mfa_token("tok1", "123456")
        assert result == {"success": True, "email": "user@example.com"}
        col.find_one_and_delete.assert_awaited_once_with({"_id": "tok1"})

    @pytest.mark.asyncio
    async def test_verify_mfa_token_is_single_use_even_on_wrong_code(self):
        """The session is consumed via find_one_and_delete on the *first*
        attempt regardless of code correctness (T-64-23 mitigation)."""
        col = _col()
        future = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(minutes=4)
        col.find_one_and_delete = AsyncMock(
            return_value={"_id": "tok1", "email": "user@example.com", "expires_at": future}
        )
        user = _hashed_password_user()
        db = _db_mock(user=user, mfa_sessions_col=col)
        with patch("mfa_service.get_database", return_value=db), \
             patch("mfa_service.verify_totp_code", return_value=False):
            result = await mfa_service.verify_mfa_token("tok1", "000000")
        assert result["success"] is False
        col.find_one_and_delete.assert_awaited_once()  # session was consumed, not left alive

    @pytest.mark.asyncio
    async def test_verify_mfa_token_missing_session_fails(self):
        col = _col()
        db = _db_mock(mfa_sessions_col=col)
        with patch("mfa_service.get_database", return_value=db):
            result = await mfa_service.verify_mfa_token("no-such-token", "123456")
        assert result == {"success": False, "error": "MFA session expired or invalid"}

    @pytest.mark.asyncio
    async def test_verify_mfa_token_expired_session_fails(self):
        col = _col()
        past = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(seconds=1)
        col.find_one_and_delete = AsyncMock(
            return_value={"_id": "tok1", "email": "user@example.com", "expires_at": past}
        )
        db = _db_mock(mfa_sessions_col=col)
        with patch("mfa_service.get_database", return_value=db):
            result = await mfa_service.verify_mfa_token("tok1", "123456")
        assert result["success"] is False


# ===========================================================================
# Enrollment
# ===========================================================================

class TestEnrollMfa:

    @pytest.mark.asyncio
    async def test_enroll_mfa_success(self):
        secret = "JBSWY3DPEHPK3PXP"
        pending_encrypted = mfa_service._encrypt_secret(secret)
        user = {"email": "user@example.com", "mfa": {"pending_secret": pending_encrypted}}
        db = _db_mock(user=user)
        with patch("mfa_service.get_database", return_value=db), \
             patch("mfa_service.verify_totp_code", return_value=True):
            result = await mfa_service.enroll_mfa("user@example.com", "123456")
        assert result["success"] is True
        assert len(result["backup_codes"]) == 8
        set_doc = db.users.update_one.call_args.args[1]["$set"]
        assert set_doc["mfa.enabled"] is True
        assert set_doc["mfa.secret_encrypted"] == pending_encrypted
        assert len(set_doc["mfa.backup_codes_hashed"]) == 8

    @pytest.mark.asyncio
    async def test_enroll_mfa_no_pending_secret(self):
        user = {"email": "user@example.com", "mfa": {}}
        db = _db_mock(user=user)
        with patch("mfa_service.get_database", return_value=db):
            result = await mfa_service.enroll_mfa("user@example.com", "123456")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_enroll_mfa_invalid_code(self):
        pending_encrypted = mfa_service._encrypt_secret("JBSWY3DPEHPK3PXP")
        user = {"email": "user@example.com", "mfa": {"pending_secret": pending_encrypted}}
        db = _db_mock(user=user)
        with patch("mfa_service.get_database", return_value=db), \
             patch("mfa_service.verify_totp_code", return_value=False):
            result = await mfa_service.enroll_mfa("user@example.com", "000000")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_enroll_mfa_user_not_found(self):
        db = _db_mock(user=None)
        with patch("mfa_service.get_database", return_value=db):
            result = await mfa_service.enroll_mfa("ghost@example.com", "123456")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_enroll_mfa_reenrollment_without_password_fails(self):
        """CR-02: re-enrolling against an already-enabled account without a
        password must not silently replace the active secret/backup codes."""
        pending_encrypted = mfa_service._encrypt_secret("JBSWY3DPEHPK3PXP")
        user = _hashed_password_user(password="Correct1!")
        user["mfa"]["pending_secret"] = pending_encrypted
        db = _db_mock(user=user)
        with patch("mfa_service.get_database", return_value=db), \
             patch("mfa_service.verify_totp_code", return_value=True):
            result = await mfa_service.enroll_mfa("user@example.com", "123456")
        assert result["success"] is False
        db.users.update_one.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_enroll_mfa_reenrollment_wrong_password_fails(self):
        pending_encrypted = mfa_service._encrypt_secret("JBSWY3DPEHPK3PXP")
        user = _hashed_password_user(password="Correct1!")
        user["mfa"]["pending_secret"] = pending_encrypted
        db = _db_mock(user=user)
        with patch("mfa_service.get_database", return_value=db), \
             patch("mfa_service.verify_totp_code", return_value=True):
            result = await mfa_service.enroll_mfa("user@example.com", "123456", "WrongPass1!")
        assert result["success"] is False
        db.users.update_one.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_enroll_mfa_reenrollment_success_with_correct_password(self):
        pending_encrypted = mfa_service._encrypt_secret("JBSWY3DPEHPK3PXP")
        user = _hashed_password_user(password="Correct1!")
        user["mfa"]["pending_secret"] = pending_encrypted
        db = _db_mock(user=user)
        with patch("mfa_service.get_database", return_value=db), \
             patch("mfa_service.verify_totp_code", return_value=True):
            result = await mfa_service.enroll_mfa("user@example.com", "123456", "Correct1!")
        assert result["success"] is True
        assert len(result["backup_codes"]) == 8


# ===========================================================================
# Disable MFA — now password-confirmed, not TOTP (breaking security tightening)
# ===========================================================================

class TestDisableMfa:

    @pytest.mark.asyncio
    async def test_disable_mfa_success_revokes_sessions(self):
        user = _hashed_password_user(password="Correct1!")
        sessions_col = _col()
        db = _db_mock(user=user, mfa_sessions_col=sessions_col)
        with patch("mfa_service.get_database", return_value=db):
            result = await mfa_service.disable_mfa("user@example.com", "Correct1!")
        assert result == {"success": True}
        set_doc = db.users.update_one.call_args.args[1]["$set"]
        assert set_doc["mfa.enabled"] is False
        assert set_doc["mfa.secret_encrypted"] is None
        assert set_doc["mfa.backup_codes_hashed"] == []
        sessions_col.delete_many.assert_awaited_once_with({"email": "user@example.com"})

    @pytest.mark.asyncio
    async def test_disable_mfa_wrong_password_fails(self):
        user = _hashed_password_user(password="Correct1!")
        db = _db_mock(user=user)
        with patch("mfa_service.get_database", return_value=db):
            result = await mfa_service.disable_mfa("user@example.com", "WrongPass1!")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_disable_mfa_not_enabled_fails(self):
        user = _hashed_password_user()
        user["mfa"]["enabled"] = False
        db = _db_mock(user=user)
        with patch("mfa_service.get_database", return_value=db):
            result = await mfa_service.disable_mfa("user@example.com", "Password1!")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_disable_mfa_no_password_on_account_fails_closed(self):
        """An SSO/LDAP-only account has no local password — must fail closed,
        not silently disable MFA without any verification."""
        user = _hashed_password_user()
        del user["password"]
        db = _db_mock(user=user)
        with patch("mfa_service.get_database", return_value=db):
            result = await mfa_service.disable_mfa("user@example.com", "anything")
        assert result["success"] is False


# ===========================================================================
# Regenerate backup codes
# ===========================================================================

class TestRegenerateBackupCodes:

    @pytest.mark.asyncio
    async def test_regenerate_success_returns_new_codes(self):
        old_hash = mfa_service._hash_backup_code("11112222")
        user = _hashed_password_user(password="Correct1!", backup_codes_hashed=[old_hash])
        db = _db_mock(user=user)
        with patch("mfa_service.get_database", return_value=db):
            result = await mfa_service.regenerate_backup_codes("user@example.com", "Correct1!")
        assert result["success"] is True
        assert len(result["backup_codes"]) == 8
        set_doc = db.users.update_one.call_args.args[1]["$set"]
        assert old_hash not in set_doc["mfa.backup_codes_hashed"]

    @pytest.mark.asyncio
    async def test_regenerate_wrong_password_fails(self):
        user = _hashed_password_user(password="Correct1!")
        db = _db_mock(user=user)
        with patch("mfa_service.get_database", return_value=db):
            result = await mfa_service.regenerate_backup_codes("user@example.com", "WrongPass1!")
        assert result["success"] is False


# ===========================================================================
# get_mfa_status
# ===========================================================================

class TestGetMfaStatus:

    @pytest.mark.asyncio
    async def test_status_reports_backup_codes_and_last_used(self):
        user = _hashed_password_user(backup_codes_hashed=["h1", "h2"], last_used_at="2026-08-13T00:00:00+00:00")
        db = _db_mock(user=user)
        with patch("mfa_service.get_database", return_value=db):
            status = await mfa_service.get_mfa_status("user@example.com")
        assert status["enabled"] is True
        assert status["backup_codes_remaining"] == 2
        assert status["has_backup_codes"] is True
        assert status["last_used"] == "2026-08-13T00:00:00+00:00"

    @pytest.mark.asyncio
    async def test_status_user_not_found_returns_disabled_defaults(self):
        db = _db_mock(user=None)
        with patch("mfa_service.get_database", return_value=db):
            status = await mfa_service.get_mfa_status("ghost@example.com")
        assert status["enabled"] is False
        assert status["has_backup_codes"] is False


# ===========================================================================
# Endpoint-level tests (mount only mfa_endpoints.router)
# ===========================================================================

class TestMFAEndpoints:

    def _app(self):
        from fastapi import FastAPI
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

    def _authed_app(self):
        from auth_types import TokenData
        from authentication_service import get_current_user

        app = self._app()
        token_data = TokenData(username="user@example.com", role="Viewer", tenant_id="t1", mfa_verified=True)
        app.dependency_overrides[get_current_user] = lambda: token_data
        return app

    def test_setup_endpoint_reenrollment_requires_password(self):
        """CR-02: POST /api/mfa/setup on an already-enabled account must
        reject without a correct password rather than silently overwriting
        mfa.pending_secret."""
        from fastapi.testclient import TestClient
        user = _hashed_password_user(password="Correct1!")
        db = _db_mock(user=user)
        app = self._authed_app()
        with patch("mfa_endpoints.get_database", return_value=db):
            with TestClient(app) as client:
                resp = client.post("/api/mfa/setup", json={})
        assert resp.status_code == 403
        db.users.update_one.assert_not_awaited()

    def test_setup_endpoint_reenrollment_succeeds_with_password(self):
        from fastapi.testclient import TestClient
        user = _hashed_password_user(password="Correct1!")
        db = _db_mock(user=user)
        app = self._authed_app()
        with patch("mfa_endpoints.get_database", return_value=db):
            with TestClient(app) as client:
                resp = client.post("/api/mfa/setup", json={"password": "Correct1!"})
        assert resp.status_code == 200
        assert "secret" in resp.json()

    def test_setup_endpoint_initial_enrollment_no_password_required(self):
        """First-time setup (MFA not yet enabled) must not require a password."""
        from fastapi.testclient import TestClient
        user = _hashed_password_user()
        user["mfa"]["enabled"] = False
        db = _db_mock(user=user)
        app = self._authed_app()
        with patch("mfa_endpoints.get_database", return_value=db):
            with TestClient(app) as client:
                resp = client.post("/api/mfa/setup", json={})
        assert resp.status_code == 200

    def test_disable_endpoint_requires_password_field(self):
        from fastapi.testclient import TestClient
        app = self._authed_app()
        with TestClient(app) as client:
            resp = client.post("/api/mfa/disable", json={"totp_code": "123456"})
        # Old field name is no longer accepted — password is required (422)
        assert resp.status_code == 422

    def test_disable_endpoint_success_with_password(self):
        from fastapi.testclient import TestClient
        app = self._authed_app()
        with patch("mfa_service.disable_mfa", new_callable=AsyncMock, return_value={"success": True}):
            with TestClient(app) as client:
                resp = client.post("/api/mfa/disable", json={"password": "Correct1!"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_disable_endpoint_wrong_password_returns_400(self):
        from fastapi.testclient import TestClient
        app = self._authed_app()
        with patch("mfa_service.disable_mfa", new_callable=AsyncMock,
                   return_value={"success": False, "error": "Invalid password"}):
            with TestClient(app) as client:
                resp = client.post("/api/mfa/disable", json={"password": "wrong"})
        assert resp.status_code == 400

    def test_backup_codes_regenerate_endpoint(self):
        from fastapi.testclient import TestClient
        app = self._authed_app()
        with patch("mfa_service.regenerate_backup_codes", new_callable=AsyncMock,
                   return_value={"success": True, "backup_codes": ["1" * 8] * 8}):
            with TestClient(app) as client:
                resp = client.post("/api/mfa/backup-codes/regenerate", json={"password": "Correct1!"})
        assert resp.status_code == 200
        assert len(resp.json()["backup_codes"]) == 8

    def test_disable_endpoint_is_rate_limited(self):
        """WR-02: /api/mfa/disable must throttle repeated attempts the same
        way /api/mfa/verify already does (5/minute)."""
        from fastapi.testclient import TestClient
        app = self._authed_app()
        with patch("mfa_service.disable_mfa", new_callable=AsyncMock,
                   return_value={"success": False, "error": "Invalid password"}):
            with TestClient(app) as client:
                statuses = [client.post("/api/mfa/disable", json={"password": "wrong"}).status_code
                            for _ in range(6)]
        assert statuses[:5] == [400] * 5
        assert statuses[5] == 429

    def test_backup_codes_regenerate_endpoint_is_rate_limited(self):
        """WR-02: /api/mfa/backup-codes/regenerate must throttle repeated
        attempts the same way /api/mfa/verify already does (5/minute)."""
        from fastapi.testclient import TestClient
        app = self._authed_app()
        with patch("mfa_service.regenerate_backup_codes", new_callable=AsyncMock,
                   return_value={"success": False, "error": "Invalid password"}):
            with TestClient(app) as client:
                statuses = [client.post("/api/mfa/backup-codes/regenerate", json={"password": "wrong"}).status_code
                            for _ in range(6)]
        assert statuses[:5] == [400] * 5
        assert statuses[5] == 429

    def test_verify_login_issues_jwt_with_mfa_verified_claim(self):
        """Regression guard: the JWT issued after MFA verification must carry
        mfa_verified=True so authentication_service.require_mfa() can pass."""
        import jwt as _jwt
        from fastapi.testclient import TestClient
        from authentication_service import SECRET_KEY, ALGORITHM

        user = _hashed_password_user()
        db = _db_mock(user=user)
        app = self._app()
        with patch("mfa_endpoints.get_database", return_value=db), \
             patch("mfa_service.verify_mfa_token", new_callable=AsyncMock,
                   return_value={"success": True, "email": "user@example.com"}):
            with TestClient(app) as client:
                resp = client.post(
                    "/api/mfa/verify",
                    json={"session_token": "valid", "code": "123456", "use_backup_code": False},
                )
        assert resp.status_code == 200
        body = resp.json()
        assert body["mfa_verified"] is True
        payload = _jwt.decode(body["access_token"], SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["mfa_verified"] is True

    def test_status_endpoint_returns_extended_fields(self):
        from fastapi.testclient import TestClient
        app = self._authed_app()
        with patch("mfa_service.get_mfa_status", new_callable=AsyncMock, return_value={
            "enabled": True, "enrolled_at": "2026-08-01T00:00:00+00:00",
            "backup_codes_remaining": 3, "has_backup_codes": True, "last_used": None,
        }):
            with TestClient(app) as client:
                resp = client.get("/api/mfa/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["has_backup_codes"] is True
        assert body["backup_codes_remaining"] == 3
